import os

os.environ["INVESTIGATOR_API_KEY"] = "test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api import impact, main  # noqa: E402
from src.api.engine import Engine  # noqa: E402
from src.rules.policy import apply_policy  # noqa: E402

KEY = {"X-API-Key": "test-key"}


def _body(eng, **over):
    r = eng.pending.iloc[0]
    b = dict(sender_id=r["sender_id"], recipient_id=r["recipient_id"], amount=500.0,
             device_id=r["sender_device_id"], timestamp=str(r["timestamp"]))
    b.update(over)
    return b


@pytest.fixture()
def env(world, tmp_path):
    db = str(tmp_path / "t.db")
    eng = Engine(str(world), str(world / "m.pkl"), db_path=db)
    main._engine = eng
    return TestClient(main.app), eng, (str(world), str(world / "m.pkl"), db)


def _hold(c, eng):
    body = _body(eng)
    eng.confirmed_fraud.add(body["recipient_id"])
    res = c.post("/v1/score", json=body).json()
    assert res["case_id"]
    return body, res


def test_state_survives_restart(env):
    c, eng, (data, model, db) = env
    body, res = _hold(c, eng)
    c.post(f"/v1/cases/{res['case_id']}/decision", headers=KEY,
           json={"decision": "reject", "investigator": "analyst1", "note": "confirmed"})
    c.post("/v1/report", json=dict(sender_id="S00001", recipient_id=body["recipient_id"], note="x"))
    eng2 = Engine(data, model, db_path=db)
    assert eng2.cases[res["case_id"]]["status"] == "rejected"
    assert body["recipient_id"] in eng2.confirmed_fraud
    assert eng2.report_count[body["recipient_id"]] == 1
    assert eng2.transfers[res["tx_ref"]]["status"] == "rejected"


def test_completed_transfer_is_replayed_into_features(env):
    c, eng, (data, model, db) = env
    r = c.post("/v1/score", json=_body(eng)).json()
    if r["action"] != "allow":
        pytest.skip("first pending transfer is not low risk in this world")
    assert c.post("/v1/confirm", json={"tx_ref": r["tx_ref"], "decision": "proceed"}).json()["status"] == "completed"
    n1 = len(eng.in_edges[_body(eng)["recipient_id"]])
    eng2 = Engine(data, model, db_path=db)
    assert len(eng2.in_edges[_body(eng)["recipient_id"]]) == n1


def test_audit_log_needs_key_and_records_decisions(env):
    c, eng, _ = env
    _, res = _hold(c, eng)
    c.post(f"/v1/cases/{res['case_id']}/decision", headers=KEY,
           json={"decision": "release", "investigator": "analyst1", "note": "ok"})
    assert c.get("/v1/audit").status_code == 401
    ev = c.get("/v1/audit?limit=50", headers=KEY).json()
    types = [e["type"] for e in ev["events"]]
    assert "case_opened" in types and "case_released" in types and ev["count"] == len(ev["events"])
    assert all(isinstance(e["detail"], str) and e["actor"] for e in ev["events"])
    assert max(e["id"] for e in ev["events"]) == ev["events"][0]["id"]      # newest first


def test_ring_action_flags_peers_and_rule_r4(env, monkeypatch):
    c, eng, _ = env
    body, res = _hold(c, eng)
    peer = next(a for a in eng.acc.index if a not in (body["recipient_id"], body["sender_id"]))
    monkeypatch.setattr(eng, "case_network", lambda cid, **k: {"peers": [{"id": peer, "reason": "shares_senders"}]})
    d = c.post(f"/v1/cases/{res['case_id']}/decision", headers=KEY,
               json={"decision": "reject", "investigator": "analyst1"}).json()
    assert d["peers_flagged"] == [peer] and peer in eng.ring_flags
    out = c.post("/v1/score", json=_body(eng, recipient_id=peer)).json()
    assert "R4_RING_PEER_OF_CONFIRMED_FRAUD" in out["triggered_rules"]
    assert out["tier"] in ("high", "extreme")
    assert out["action"] in ("warn_cooloff", "hold_for_review")


def test_policy_r4_only_raises_and_never_holds():
    p = apply_policy("low", 100, 0, False, True)
    assert p["final_tier"] == "high" and p["action"] == "warn_cooloff"
    assert apply_policy("extreme", 100, 0, False, True)["final_tier"] == "extreme"
    assert "R4_RING_PEER_OF_CONFIRMED_FRAUD" not in apply_policy("low", 100, 0, True, True)["triggered_rules"]


def test_recovery_lists_earlier_senders(env):
    c, eng, _ = env
    _, res = _hold(c, eng)
    rec = c.get(f"/v1/cases/{res['case_id']}/recovery", headers=KEY).json()
    assert set(rec) >= {"case_id", "recipient_id", "earlier_senders", "earlier_total_tk", "this_transfer_tk",
                        "peers_flagged", "notify_count"}
    assert rec["notify_count"] == len(rec["earlier_senders"])
    assert rec["earlier_total_tk"] == sum(x["amount_tk"] for x in rec["earlier_senders"])
    assert c.get(f"/v1/cases/{res['case_id']}/recovery").status_code == 401
    assert c.get("/v1/cases/C9999/recovery", headers=KEY).status_code == 404


def test_impact_calculator(env):
    c, _, _ = env
    r = c.get("/v1/impact").json()
    res = r["results"]
    assert res["net_benefit_tk"] == res["prevented_value_tk"] - res["revenue_lost_tk"] - res["investigator_cost_tk"] \
        or abs(res["net_benefit_tk"] - (res["prevented_value_tk"] - res["revenue_lost_tk"] - res["investigator_cost_tk"])) <= 2
    assert 0 <= res["break_even_warn_effect"] <= 1 and len(r["sensitivity"]) == 9
    nets = [s["net_benefit_tk"] for s in r["sensitivity"]]
    assert nets == sorted(nets) and "Assumption" in r["disclaimer"] and r["pilot"]["n_per_arm"] > 0
    assert r["inputs"]["warn_effect"] == 0.5
    zero = c.get("/v1/impact?warn_effect=0").json()["results"]
    assert zero["prevented_value_tk"] == 0 and zero["net_benefit_tk"] < 0
    assert c.get("/v1/impact?recall=2").status_code == 422


def test_pilot_sample_size_grows_for_smaller_effects():
    assert impact.pilot_sample_size(0.007, 0.15) > impact.pilot_sample_size(0.007, 0.30) > impact.pilot_sample_size(0.007, 0.5)


def test_rate_limit_and_security_headers(env, monkeypatch):
    c, eng, _ = env
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    main._hits.clear()
    codes = [c.get("/v1/metrics").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")
    h = c.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "default-src 'self'" in h["content-security-policy"]
    assert c.get("/v1/metrics").headers["cache-control"] == "no-store"
