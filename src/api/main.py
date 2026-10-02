"""Safe-Send real-time API (FastAPI).

Run:  uvicorn src.api.main:app --port 8000
Docs: http://localhost:8000/docs

Public (sender app):   /v1/score  /v1/confirm  /v1/report  /v1/transfers/{ref}
Investigator (key):    /v1/cases  /v1/cases/{id}  /v1/cases/{id}/network  /v1/cases/{id}/decision
Ops:                   /health  /v1/metrics
Demo helpers:          /v1/demo/examples  /v1/demo/load/{example_id}
"""
from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.api.engine import Engine

DATA_DIR = os.getenv("DATA_DIR", "data")
MODEL_PATH = os.getenv("MODEL_PATH", "models/risk_model.pkl")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
INVESTIGATOR_API_KEY = os.getenv("INVESTIGATOR_API_KEY", "")

@asynccontextmanager
async def lifespan(_app):
    """Load model, feature store and history once at start-up (not on the first user request)."""
    if os.getenv("EAGER_LOAD", "1") == "1":
        get_engine()
    yield


app = FastAPI(title="Safe-Send Recipient Risk Check", version="1.0.0", lifespan=lifespan,
              description="Scores a transfer before confirmation. Nothing is auto-blocked: "
                          "the most severe outcome is a hold that a human investigator decides.")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine(DATA_DIR, MODEL_PATH)
    return _engine


def require_investigator(x_api_key: str = Header(default="")) -> None:
    """Access control for investigator endpoints (API key from the environment)."""
    if not INVESTIGATOR_API_KEY or not secrets.compare_digest(x_api_key, INVESTIGATOR_API_KEY):
        raise HTTPException(status_code=401, detail="investigator API key required")


# ------------------------------------------------------------------ schemas
class ScoreRequest(BaseModel):
    sender_id: str = Field(min_length=3, max_length=32)
    recipient_id: str = Field(min_length=3, max_length=32)
    amount: float = Field(gt=0, le=1_000_000)
    tx_type: Literal["send_money", "merchant_payment"] = "send_money"
    channel: Literal["app", "ussd"] = "app"
    device_id: str | None = Field(default=None, max_length=64)
    timestamp: str | None = None          # simulation clock; defaults to "now" of the demo data
    lang: Literal["en", "bn"] = "en"


class ConfirmRequest(BaseModel):
    tx_ref: str
    decision: Literal["proceed", "cancel"]


class ReportRequest(BaseModel):
    sender_id: str
    recipient_id: str
    tx_ref: str | None = None
    note: str = Field(default="", max_length=300)


class DecisionRequest(BaseModel):
    decision: Literal["release", "reject"]
    investigator: str = Field(min_length=2, max_length=64)
    note: str = Field(default="", max_length=500)


def _wrap(fn, *a):
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0]))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except TimeoutError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


# ------------------------------------------------------------------ public
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/score")
def score(req: ScoreRequest, eng: Engine = Depends(get_engine)):
    body = req.model_dump()
    return _wrap(eng.score, body, req.lang)


@app.post("/v1/confirm")
def confirm(req: ConfirmRequest, eng: Engine = Depends(get_engine)):
    return _wrap(eng.confirm, req.tx_ref, req.decision)


@app.post("/v1/report")
def report(req: ReportRequest, eng: Engine = Depends(get_engine)):
    return _wrap(eng.report, req.recipient_id, req.sender_id, req.tx_ref, req.note)


@app.get("/v1/transfers/{tx_ref}")
def transfer(tx_ref: str, eng: Engine = Depends(get_engine)):
    rec = eng.transfers.get(tx_ref)
    if rec is None:
        raise HTTPException(404, "unknown tx_ref")
    return {"tx_ref": tx_ref, "status": rec["status"], "tier": rec["tier"], "case_id": rec["case_id"]}


# ------------------------------------------------------------------ investigator
@app.get("/v1/cases", dependencies=[Depends(require_investigator)])
def cases(status: str | None = Query(default=None), eng: Engine = Depends(get_engine)):
    items = [c for c in eng.cases.values() if status is None or c["status"] == status]
    return {"count": len(items), "cases": sorted(items, key=lambda c: -c["risk_score"])}


@app.get("/v1/cases/{case_id}", dependencies=[Depends(require_investigator)])
def case(case_id: str, eng: Engine = Depends(get_engine)):
    c = eng.cases.get(case_id)
    if c is None:
        raise HTTPException(404, "unknown case")
    return c


@app.get("/v1/cases/{case_id}/network", dependencies=[Depends(require_investigator)])
def case_network(case_id: str, days: int = Query(default=7, ge=1, le=30),
                 max_senders: int = Query(default=40, ge=5, le=100), eng: Engine = Depends(get_engine)):
    """Transaction neighbourhood of the recipient (NetworkX): senders, payouts, peer accounts, shared devices."""
    return _wrap(eng.case_network, case_id, days, max_senders)


@app.post("/v1/cases/{case_id}/decision", dependencies=[Depends(require_investigator)])
def decide(case_id: str, req: DecisionRequest, eng: Engine = Depends(get_engine)):
    return _wrap(eng.decide, case_id, req.decision, req.investigator, req.note)


# ------------------------------------------------------------------ ops and demo
@app.get("/v1/metrics")
def metrics(eng: Engine = Depends(get_engine)):
    return eng.metrics()


@app.get("/v1/demo/examples")
def demo_examples(eng: Engine = Depends(get_engine)):
    return {"examples": eng.examples}


@app.post("/v1/demo/load/{example_id}")
def demo_load(example_id: str, eng: Engine = Depends(get_engine)):
    """Advance the simulation to just before the example and return a ready-to-send score request."""
    return _wrap(eng.load_example, example_id)


# ------------------------------------------------------------------ optional: serve the built React app
def mount_frontend(application: FastAPI, dist: Path) -> bool:
    """Serve a built single-page app from the same origin (one URL, no CORS).

    API routes (/v1, /docs, /health) keep priority. Any other path returns index.html
    so client-side routes such as /investigator work on refresh.
    """
    dist = Path(dist).resolve()
    if not (dist / "index.html").is_file():
        return False

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("v1/", "docs", "openapi", "redoc")):
            raise HTTPException(404, "not found")
        f = (dist / full_path).resolve()
        if full_path and f.is_file() and str(f).startswith(str(dist)):
            return FileResponse(f)
        return FileResponse(dist / "index.html")

    return True


mount_frontend(app, Path(os.getenv("FRONTEND_DIST", "frontend/dist")))
