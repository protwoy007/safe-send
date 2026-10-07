"""Concurrent load test against a running Safe-Send API.

    RATE_LIMIT_PER_MIN=0 python -m uvicorn src.api.main:app --port 8000     # terminal 1
    python scripts/load_test.py --url http://localhost:8000 --n 1500 --concurrency 20   # terminal 2
"""
import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--concurrency", type=int, default=20)
    a = ap.parse_args()

    tx = pd.read_csv("data/transactions.csv", parse_dates=["timestamp"])
    tx = tx[tx["tx_type"].isin(["send_money", "merchant_payment"])].tail(20000).sample(a.n, random_state=1)
    bodies = [dict(sender_id=r.sender_id, recipient_id=r.recipient_id, amount=float(r.amount), tx_type=r.tx_type,
                   channel=r.channel, device_id=r.sender_device_id, timestamp=str(r.timestamp)) for r in tx.itertuples()]
    lat, codes = [], []

    def call(b):
        with httpx.Client(base_url=a.url, timeout=30) as c:
            t = time.perf_counter()
            r = c.post("/v1/score", json=b)
            return (time.perf_counter() - t) * 1000, r.status_code

    def worker(chunk):
        with httpx.Client(base_url=a.url, timeout=30) as c:
            out = []
            for b in chunk:
                t = time.perf_counter()
                r = c.post("/v1/score", json=b)
                out.append(((time.perf_counter() - t) * 1000, r.status_code))
            return out

    chunks = [bodies[i::a.concurrency] for i in range(a.concurrency)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.concurrency) as ex:
        for res in ex.map(worker, chunks):
            for ms, code in res:
                lat.append(ms); codes.append(code)
    wall = time.perf_counter() - t0
    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))]
    ok = sum(c == 200 for c in codes)
    print(f"requests={len(codes)} ok={ok} errors={len(codes) - ok} concurrency={a.concurrency}")
    print(f"throughput={len(codes) / wall:.0f} req/s  p50={q(.5):.1f} ms  p95={q(.95):.1f} ms  p99={q(.99):.1f} ms  max={lat[-1]:.1f} ms")


if __name__ == "__main__":
    main()
