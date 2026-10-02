"""Measure scoring latency (target: about 200 ms per request).

    python scripts/benchmark_latency.py --n 300
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient  # noqa: E402

from src.api.main import app, get_engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    n = ap.parse_args().n
    client = TestClient(app)
    eng = get_engine()
    pend = eng.pending.sample(n, random_state=0)
    lat = []
    for r in pend.itertuples(index=False):
        body = dict(sender_id=r.sender_id, recipient_id=r.recipient_id, amount=float(r.amount),
                    tx_type=r.tx_type if r.tx_type in ("send_money", "merchant_payment") else "send_money",
                    channel=r.channel, device_id=r.sender_device_id, timestamp=str(r.timestamp))
        t = time.perf_counter()
        res = client.post("/v1/score", json=body)
        lat.append((time.perf_counter() - t) * 1000)
        assert res.status_code == 200, res.text
    lat = np.array(lat)
    print(f"requests={n}  p50={np.percentile(lat, 50):.1f} ms  p95={np.percentile(lat, 95):.1f} ms  "
          f"p99={np.percentile(lat, 99):.1f} ms  max={lat.max():.1f} ms  (target 200 ms)")


if __name__ == "__main__":
    main()
