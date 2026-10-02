"""Serving engine: feature store + model + explanations + policy + case queue.

State lives in memory (prototype). Production would use a feature store, a database
and a message queue; the interfaces here are designed so those can be swapped in.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.explain.reasons import Explainer
from src.features.build import FEATURES, FeatureStore, load
from src.rules.policy import COOLOFF_SECONDS, apply_policy

WARM_UNTIL_DAY = 50   # history replayed at start-up; later transactions are used for live demos


class Engine:
    def __init__(self, data_dir: str = "data", model_path: str = "models/risk_model.pkl",
                 warm_until_day: int = WARM_UNTIL_DAY, clock=time.monotonic):
        self.clock = clock
        acc, tx = load(data_dir)
        self.acc = acc.set_index("account_id")
        tx = tx.sort_values("timestamp", kind="stable").reset_index(drop=True)
        day = (tx["timestamp"] - tx["timestamp"].min().normalize()).dt.days
        self._acc_df = acc
        self.explainer = Explainer.from_pickle(model_path)
        self._row = lambda r: dict(sender_id=r.sender_id, recipient_id=r.recipient_id, amount=r.amount,
                                   tx_type=r.tx_type, sender_device_id=r.sender_device_id, channel=r.channel)
        self.warm = tx[day < warm_until_day].reset_index(drop=True)
        self.pending = tx[day >= warm_until_day].reset_index(drop=True)   # not yet "happened"
        self._reset_store()
        self.feat_all = pd.read_csv(Path(data_dir) / "features.csv", parse_dates=["timestamp"])
        self.transfers: dict[str, dict] = {}
        self.cases: dict[str, dict] = {}
        self.reports: list[dict] = []
        self.report_count: dict[str, int] = {}
        self.confirmed_fraud: set[str] = set()
        self.latencies: list[float] = []
        self.tier_counts = {"low": 0, "medium": 0, "high": 0, "extreme": 0}
        self.examples: list[dict] = []
        self._build_examples()

    def _reset_store(self) -> None:
        """(Re)build the feature store from the warm-up history only."""
        self.store = FeatureStore(self._acc_df)
        for r in self.warm.itertuples(index=False):
            self.store.commit(self._row(r), r.timestamp)
        self.ptr = 0

    # ------------------------------------------------------------ scoring
    def score(self, req: dict, lang: str = "en") -> dict:
        t0 = time.perf_counter()
        for k in ("sender_id", "recipient_id"):
            if not self.store.known(req[k]):
                raise KeyError(f"unknown account: {req[k]}")
        ts = pd.Timestamp(req["timestamp"]) if req.get("timestamp") else (
            (self.store.last_ts or pd.Timestamp("2026-07-01")) + pd.Timedelta(minutes=1))
        tx = dict(sender_id=req["sender_id"], recipient_id=req["recipient_id"], amount=req["amount"],
                  tx_type=req.get("tx_type", "send_money"), channel=req.get("channel", "app"),
                  sender_device_id=req.get("device_id") or f"unknown-{req['sender_id']}")
        X = pd.DataFrame([self.store.features(tx, ts)])[FEATURES]
        e = self.explainer.explain(X, lang=lang)[0]
        pol = apply_policy(e["tier"], tx["amount"], self.report_count.get(tx["recipient_id"], 0),
                           tx["recipient_id"] in self.confirmed_fraud)

        ref = "T" + uuid.uuid4().hex[:10]
        status = {"allow": "ready", "warn": "ready", "warn_cooloff": "ready", "hold_for_review": "pending_review"}[pol["action"]]
        rec = dict(tx_ref=ref, tx=tx, ts=ts, status=status, scored_at=self.clock(), cooloff=pol["cooloff_seconds"],
                   risk_score=e["risk_score"], tier=pol["final_tier"], reasons=e["reasons"], case_id=None)
        self.transfers[ref] = rec
        if pol["action"] == "hold_for_review":
            rec["case_id"] = self._open_case(rec, e, pol)
        self.tier_counts[pol["final_tier"]] += 1
        ms = (time.perf_counter() - t0) * 1000
        self.latencies.append(ms)
        return {"tx_ref": ref, "risk_score": e["risk_score"], "model_tier": pol["model_tier"],
                "tier": pol["final_tier"], "action": pol["action"], "cooloff_seconds": pol["cooloff_seconds"],
                "message": self.explainer_msg(pol["final_tier"], lang), "reasons": e["reasons"],
                "triggered_rules": pol["triggered_rules"], "can_report": pol["can_report"],
                "case_id": rec["case_id"], "status": status, "latency_ms": round(ms, 1),
                "explanation_source": e["explanation_source"]}

    @staticmethod
    def explainer_msg(tier: str, lang: str) -> str:
        from src.explain.reasons import ACTIONS
        return ACTIONS[lang][tier]

    # ------------------------------------------------------------ confirm / report
    def confirm(self, tx_ref: str, decision: str) -> dict:
        rec = self.transfers.get(tx_ref)
        if rec is None:
            raise KeyError("unknown tx_ref")
        if rec["status"] in ("completed", "cancelled", "rejected"):
            raise ValueError(f"transfer already {rec['status']}")
        if decision == "cancel":
            rec["status"] = "cancelled"
            return {"tx_ref": tx_ref, "status": "cancelled"}
        if rec["status"] == "pending_review":
            raise PermissionError("transfer is on hold; only an investigator can release it")
        waited = self.clock() - rec["scored_at"]
        if waited < rec["cooloff"]:
            raise TimeoutError(f"cool-off active: {rec['cooloff'] - waited:.0f}s remaining")
        self._complete(rec)
        return {"tx_ref": tx_ref, "status": "completed"}

    def _complete(self, rec: dict) -> None:
        self.store.commit(rec["tx"], rec["ts"])
        rec["status"] = "completed"

    def report(self, recipient_id: str, sender_id: str, tx_ref: str | None, note: str) -> dict:
        if not self.store.known(recipient_id):
            raise KeyError("unknown account")
        self.reports.append(dict(recipient_id=recipient_id, sender_id=sender_id, tx_ref=tx_ref, note=note[:300]))
        self.report_count[recipient_id] = self.report_count.get(recipient_id, 0) + 1
        return {"recipient_id": recipient_id, "total_reports": self.report_count[recipient_id]}

    # ------------------------------------------------------------ investigator cases
    def _open_case(self, rec, e, pol) -> str:
        cid = f"C{len(self.cases) + 1:04d}"
        tx = rec["tx"]
        self.cases[cid] = dict(
            case_id=cid, tx_ref=rec["tx_ref"], status="pending_review", sender_id=tx["sender_id"],
            recipient_id=tx["recipient_id"], amount=tx["amount"], timestamp=str(rec["ts"]),
            risk_score=e["risk_score"], tier=pol["final_tier"], triggered_rules=pol["triggered_rules"],
            reasons=e["reasons"], decision=None, investigator=None, note=None)
        return cid

    def decide(self, case_id: str, decision: str, investigator: str, note: str) -> dict:
        case = self.cases.get(case_id)
        if case is None:
            raise KeyError("unknown case")
        if case["status"] != "pending_review":
            raise ValueError(f"case already {case['status']}")
        rec = self.transfers[case["tx_ref"]]
        case.update(decision=decision, investigator=investigator, note=note[:500])
        if decision == "release":
            self._complete(rec)
            case["status"] = "released"
        else:   # "reject": transfer not executed; recipient flagged as confirmed fraud
            rec["status"] = "rejected"
            case["status"] = "rejected"
            self.confirmed_fraud.add(case["recipient_id"])
        return case

    # ------------------------------------------------------------ demo support
    def _build_examples(self) -> None:
        """Pick one representative example per pattern from the not-yet-happened period."""
        f = self.feat_all[self.feat_all["tx_id"].isin(self.pending["tx_id"])].copy()
        f = f[f["scorable"] == 1]
        f["score"] = self.explainer.score(f)
        med = self.explainer.thr["medium"]
        picks = [("normal", "A normal payment", f[(f.scam_pattern == "normal") & (f.score < med)]),
                 ("legit_return", "A genuine return to the original sender", f[(f.scam_pattern == "legit_return") & (f.score < med)]),
                 ("return_scam", "Karim: returning 'mistaken' money to a stranger", f[f.scam_pattern == "return_scam"]),
                 ("mule", "Sending to a mule account", f[f.scam_pattern == "mule"]),
                 ("ato", "Account takeover: new device, large amount", f[f.scam_pattern == "ato"]),
                 ("split", "Draining an account in small pieces", f[f.scam_pattern == "split"]),
                 ("false_alarm", "Legitimate transfer that is warned (false alarm)",
                  f[(f.is_scam == 0) & (f.score >= med) & (f.scam_pattern.str.startswith("legit"))])]
        for key, title, sub in picks:
            if len(sub) == 0:
                continue
            row = sub.iloc[(sub["score"] - sub["score"].median()).abs().argsort().iloc[0]]   # typical case
            self.examples.append(dict(example_id=key, title=title, tx_id=row["tx_id"]))

    def load_example(self, example_id: str) -> dict:
        ex = next((e for e in self.examples if e["example_id"] == example_id), None)
        if ex is None:
            raise KeyError("unknown example")
        idx = int(self.pending.index[self.pending["tx_id"] == ex["tx_id"]][0])
        if idx < self.ptr:               # going back in time: rebuild state from the warm-up history
            self._reset_store()
        while self.ptr < idx:            # replay everything that happened before this transfer
            r = self.pending.iloc[self.ptr]
            self.store.commit(self._row(r), r["timestamp"])
            self.ptr += 1
        r = self.pending.iloc[idx]
        return dict(sender_id=r["sender_id"], recipient_id=r["recipient_id"], amount=float(r["amount"]),
                    tx_type=r["tx_type"], channel=r["channel"], device_id=r["sender_device_id"],
                    timestamp=str(r["timestamp"]))

    # ------------------------------------------------------------ monitoring
    def metrics(self) -> dict:
        lat = np.array(self.latencies) if self.latencies else np.array([0.0])
        return {"requests": len(self.latencies), "tier_counts": self.tier_counts,
                "latency_ms": {"p50": round(float(np.percentile(lat, 50)), 1),
                               "p95": round(float(np.percentile(lat, 95)), 1),
                               "max": round(float(lat.max()), 1), "target": 200},
                "open_cases": sum(c["status"] == "pending_review" for c in self.cases.values()),
                "reports": len(self.reports), "thresholds": self.explainer.thr,
                "cooloff_seconds": COOLOFF_SECONDS}
