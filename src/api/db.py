"""Persistent storage and append-only audit log (SQLite).

State that must survive a restart is stored here: transfers, investigator cases,
sender reports, confirmed-fraud and ring flags, and the audit log. The Store is a small
JSON-document layer so the same interface can be backed by PostgreSQL in production
(set DB_PATH to a file for SQLite; use ":memory:" for tests).

The audit table is append-only: this module has no update or delete for it.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DOC_TABLES = ("transfers", "cases")


def _jsonable(o):
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)


def dumps(doc) -> str:
    return json.dumps(doc, default=_jsonable, ensure_ascii=False)


class Store:
    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=OFF")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS transfers (key TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cases (key TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS flags (recipient_id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_case TEXT, ts TEXT);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, type TEXT NOT NULL,
                actor TEXT NOT NULL, tx_ref TEXT, case_id TEXT, detail TEXT);
        """)
        self._db.commit()

    # ---------------------------------------------------------------- documents
    def put(self, table: str, key: str, doc: dict) -> None:
        assert table in DOC_TABLES
        with self._lock:
            self._db.execute(f"INSERT INTO {table}(key, doc) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET doc=excluded.doc",
                             (key, dumps(doc)))
            self._db.commit()

    def all(self, table: str) -> list[dict]:
        assert table in DOC_TABLES
        with self._lock:
            rows = self._db.execute(f"SELECT doc FROM {table} ORDER BY rowid").fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_report(self, doc: dict) -> None:
        with self._lock:
            self._db.execute("INSERT INTO reports(doc) VALUES(?)", (dumps(doc),))
            self._db.commit()

    def reports(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT doc FROM reports ORDER BY id").fetchall()
        return [json.loads(r[0]) for r in rows]

    # ---------------------------------------------------------------- flags
    def set_flag(self, recipient_id: str, kind: str, source_case: str | None) -> None:
        with self._lock:
            self._db.execute("INSERT INTO flags(recipient_id, kind, source_case, ts) VALUES(?,?,?,?) "
                             "ON CONFLICT(recipient_id) DO UPDATE SET kind=excluded.kind, source_case=excluded.source_case",
                             (recipient_id, kind, source_case, _now()))
            self._db.commit()

    def flags(self) -> list[tuple]:
        with self._lock:
            return self._db.execute("SELECT recipient_id, kind, source_case FROM flags").fetchall()

    # ---------------------------------------------------------------- audit (append-only)
    def audit(self, type_: str, actor: str, tx_ref: str | None = None, case_id: str | None = None,
              detail: str = "") -> dict:
        ts = _now()
        with self._lock:
            cur = self._db.execute("INSERT INTO audit(ts, type, actor, tx_ref, case_id, detail) VALUES(?,?,?,?,?,?)",
                                   (ts, type_, actor, tx_ref, case_id, detail))
            self._db.commit()
        return {"id": cur.lastrowid, "ts": ts, "type": type_, "actor": actor, "tx_ref": tx_ref,
                "case_id": case_id, "detail": detail}

    def audit_list(self, limit: int = 50, type_: str | None = None) -> list[dict]:
        q, args = "SELECT id, ts, type, actor, tx_ref, case_id, detail FROM audit", []
        if type_:
            q += " WHERE type = ?"
            args.append(type_)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        keys = ("id", "ts", "type", "actor", "tx_ref", "case_id", "detail")
        return [dict(zip(keys, r)) for r in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
