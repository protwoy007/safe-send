import os

os.environ["INVESTIGATOR_API_KEY"] = "test-key"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api import main  # noqa: E402
from src.api.engine import Engine  # noqa: E402
from src.api.network import build_network  # noqa: E402

KEY = {"X-API-Key": "test-key"}


@pytest.fixture()
def eng(world):
    return Engine(str(world), str(world / "m.pkl"), db_path=":memory:")


def _tx(s, r, amt=1000.0, dev="D-test"):
    return dict(sender_id=s, recipient_id=r, amount=amt, tx_type="send_money", sender_device_id=dev, channel="app")


def test_ring_peers_and_device_links_are_found(eng):
    ids = list(eng.acc.index[:12])
    senders, m1, m2, agent = ids[:5], ids[5], ids[6], ids[7]
    base = eng.store.last_ts + pd.Timedelta(hours=1)
    for i, s in enumerate(senders):                         # 5 senders each pay BOTH mules
        eng._commit(_tx(s, m1, 800), base + pd.Timedelta(minutes=i))
        eng._commit(_tx(s, m2, 900), base + pd.Timedelta(minutes=10 + i))
    eng._commit(_tx(m1, agent, 3000), base + pd.Timedelta(minutes=40))   # pay-out after receiving
    eng._commit(_tx(ids[8], ids[9], 100, dev="SHARED"), base)
    eng._commit(_tx(ids[10], ids[9], 100, dev="SHARED"), base)
    now = base + pd.Timedelta(hours=2)
    net = build_network(eng, m1, ids[8], now, 5000, "SHARED")
    peers = {p["id"]: p["reason"] for p in net["peers"]}
    assert peers.get(m2) == "shares_senders"
    assert net["metrics"]["distinct_senders_incl_this"] >= 6
    pay = [e for e in net["edges"] if e["source"] == m1 and e["target"] == agent]
    assert pay and pay[0]["amount"] >= 3000                      # pay-out after receiving is shown
    assert net["metrics"]["outflow_tk"] >= 3000
    assert net["metrics"]["shared_devices"] == 1
    assert any(n["role"] == "device" for n in net["nodes"])
    assert any("coordinated ring" in n for n in net["notes"])
    assert any(e["kind"] == "pending" for e in net["edges"])


def test_network_uses_only_past_data(eng):
    ids = list(eng.acc.index[:4])
    t = eng.store.last_ts + pd.Timedelta(hours=1)
    eng._commit(_tx(ids[0], ids[1], 500), t + pd.Timedelta(hours=5))      # in the FUTURE of the review time
    net = build_network(eng, ids[1], ids[2], t, 700, None)
    assert all(e["kind"] == "pending" for e in net["edges"] if e["target"] == ids[1])


def test_endpoint_auth_shape_and_no_ground_truth(world, eng):
    main._engine = eng
    c = TestClient(main.app)
    req = c.post("/v1/demo/load/mule").json()
    eng.confirmed_fraud.add(req["recipient_id"])
    res = c.post("/v1/score", json=req).json()
    cid = res["case_id"]
    assert c.get(f"/v1/cases/{cid}/network").status_code == 401
    assert c.get("/v1/cases/C9999/network", headers=KEY).status_code == 404
    net = c.get(f"/v1/cases/{cid}/network?days=7", headers=KEY).json()
    node_ids = {n["id"] for n in net["nodes"]}
    assert {req["recipient_id"], req["sender_id"]} <= node_ids
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in net["edges"])
    assert "gt_" not in str(net) and "mule" not in {n["role"] for n in net["nodes"]}
    assert net["notes"] and "metrics" in net
