import os

os.environ["INVESTIGATOR_API_KEY"] = "test-key"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api import main  # noqa: E402
from src.api.engine import Engine  # noqa: E402
from src.features.build import FEATURES  # noqa: E402
from src.rules.policy import LARGE_AMOUNT_LIMIT, apply_policy  # noqa: E402

KEY = {"X-API-Key": "test-key"}


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture()
def api(world):
    clock = FakeClock()
    eng = Engine(str(world), str(world / "m.pkl"), clock=clock)
    main._engine = eng
    return TestClient(main.app), eng, clock


def _req(eng, **over):
    r = eng.pending.iloc[0]
    body = dict(sender_id=r["sender_id"], recipient_id=r["recipient_id"], amount=500.0,
                device_id=r["sender_device_id"], timestamp=str(r["timestamp"]))
    body.update(over)
    return body


def test_health_and_validation(api):
    c, eng, _ = api
    assert c.get("/health").json() == {"status": "ok"}
    assert c.post("/v1/score", json=_req(eng, amount=-5)).status_code == 422
    assert c.post("/v1/score", json=_req(eng, recipient_id="NOPE999")).status_code == 404


def test_policy_only_raises_tier():
    p = apply_policy("low", 50_000, 0, False)
    assert p["final_tier"] == "high" and "R1_LARGE_AMOUNT" in p["triggered_rules"]
    assert apply_policy("extreme", 100, 0, False)["final_tier"] == "extreme"
    assert apply_policy("low", 100, 3, False)["final_tier"] == "high"
    assert apply_policy("low", 100, 0, True)["final_tier"] == "extreme"


def test_cooloff_is_enforced_server_side(api):
    c, eng, clock = api
    res = c.post("/v1/score", json=_req(eng, amount=LARGE_AMOUNT_LIMIT + 1)).json()
    assert res["action"] in ("warn_cooloff", "hold_for_review")
    if res["action"] == "warn_cooloff":
        ref = res["tx_ref"]
        r = c.post("/v1/confirm", json={"tx_ref": ref, "decision": "proceed"})
        assert r.status_code == 409 and "cool-off" in r.json()["detail"]
        clock.t += 31
        assert c.post("/v1/confirm", json={"tx_ref": ref, "decision": "proceed"}).json()["status"] == "completed"
        assert c.post("/v1/confirm", json={"tx_ref": ref, "decision": "proceed"}).status_code == 409


def test_hold_requires_human_and_investigator_auth(api):
    c, eng, _ = api
    body = _req(eng)
    eng.confirmed_fraud.add(body["recipient_id"])           # setup: recipient confirmed as fraud earlier
    res = c.post("/v1/score", json=body).json()
    assert res["action"] == "hold_for_review" and res["case_id"]
    assert "R3_INVESTIGATOR_CONFIRMED_FRAUD" in res["triggered_rules"]
    # sender cannot push a held transfer through
    assert c.post("/v1/confirm", json={"tx_ref": res["tx_ref"], "decision": "proceed"}).status_code == 403
    # investigator endpoints need the key
    assert c.get("/v1/cases").status_code == 401
    assert c.get("/v1/cases", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/v1/cases", headers=KEY).json()["count"] == 1
    # human decision releases it
    d = c.post(f"/v1/cases/{res['case_id']}/decision", headers=KEY,
               json={"decision": "release", "investigator": "analyst1", "note": "verified with sender"}).json()
    assert d["status"] == "released"
    assert c.get(f"/v1/transfers/{res['tx_ref']}").json()["status"] == "completed"
    assert c.post(f"/v1/cases/{res['case_id']}/decision", headers=KEY,
                  json={"decision": "reject", "investigator": "analyst1"}).status_code == 409


def test_repeated_reports_raise_tier(api):
    c, eng, _ = api
    body = _req(eng)
    for i in range(3):
        c.post("/v1/report", json=dict(sender_id=f"X{i}0000", recipient_id=body["recipient_id"], note="scam call"))
    res = c.post("/v1/score", json=body).json()
    assert "R2_REPEATED_USER_REPORTS" in res["triggered_rules"]
    assert res["tier"] in ("high", "extreme")


def test_serving_features_match_training_features(api):
    """No training/serving skew: replayed live state gives the same features as the batch build."""
    _, eng, _ = api
    assert eng.examples
    for ex in eng.examples:
        req = eng.load_example(ex["example_id"])
        tx = dict(sender_id=req["sender_id"], recipient_id=req["recipient_id"], amount=req["amount"],
                  tx_type=req["tx_type"], channel=req["channel"], sender_device_id=req["device_id"])
        live = eng.store.features(tx, pd.Timestamp(req["timestamp"]))
        batch = eng.feat_all[eng.feat_all["tx_id"] == ex["tx_id"]].iloc[0]
        a = np.array([live[f] for f in FEATURES], dtype=float)
        b = batch[FEATURES].to_numpy(dtype=float)
        assert np.allclose(a, b, equal_nan=True), ex["example_id"]


def test_metrics_and_latency(api):
    c, eng, _ = api
    for r in eng.pending.head(20).itertuples(index=False):
        c.post("/v1/score", json=dict(sender_id=r.sender_id, recipient_id=r.recipient_id, amount=float(r.amount),
                                      tx_type="send_money", device_id=r.sender_device_id, timestamp=str(r.timestamp)))
    m = c.get("/v1/metrics").json()
    assert m["requests"] == 20 and m["latency_ms"]["p95"] < 200


def test_bangla_response(api):
    c, eng, _ = api
    res = c.post("/v1/score", json=_req(eng, lang="bn", amount=LARGE_AMOUNT_LIMIT + 1)).json()
    assert any("\u0980" <= ch <= "\u09FF" for ch in res["message"])
