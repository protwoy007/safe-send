"""Leakage-free feature builder for Safe-Send.

Every feature for a transaction is computed ONLY from information available
strictly before that transaction (a single time-ordered pass keeps running
state, features are read first, then the state is updated). This mirrors what
the real-time API can know at confirmation time.

Feature groups
    tabular   : amount, time-of-day, sender history, new recipient / new device
    network   : recipient fan-in (distinct senders), recipient in/out balance,
                recipient cash-out history, devices shared across senders
    scam cues : "returning money you just received" (and whether it goes back
                to the ORIGINAL sender, which is the legitimate case)

Ground-truth columns (`is_scam`, `scam_pattern`) are carried through for
training/evaluation only. They are never part of FEATURES.

Usage:
    python -m src.features.build --data data --out data/features.csv
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

H = 3600
EPOCH = pd.Timestamp("1970-01-01")

FEATURES = [
    # tabular
    "amount", "log_amount", "hour", "is_night", "day_of_week", "is_month_end",
    "is_ussd", "is_merchant_payment", "recipient_is_merchant", "recipient_is_agent",
    "sender_age_h", "recipient_age_h",
    "sender_tx_count_prior", "sender_mean_amount_prior", "amount_to_mean_ratio",
    "sender_tx_15m", "sender_amount_15m", "sender_tx_1h",
    "pair_count_prior", "is_new_recipient", "is_new_device", "device_shared_senders",
    # network
    "recipient_senders_1h", "recipient_senders_24h", "recipient_senders_all",
    "recipient_in_count_1h", "recipient_out_count_prior", "recipient_in_out_ratio",
    "recipient_cashout_prior",
    # scam cues
    "sender_received_3h", "returning_recent_received", "return_to_original_sender",
]
META = ["tx_id", "timestamp", "sender_id", "recipient_id", "tx_type", "is_scam",
        "scam_pattern", "scorable"]
NOT_SCORED = {"mule_cashout", "return_setup"}  # fraudsters' own actions, not sender-side checks


def _seconds(s: pd.Series) -> np.ndarray:
    return (s - EPOCH).dt.total_seconds().to_numpy()


def load(data_dir: str | Path = "data") -> tuple[pd.DataFrame, pd.DataFrame]:
    d = Path(data_dir)
    acc = pd.read_csv(d / "accounts.csv", parse_dates=["created_ts"])
    tx = pd.read_csv(d / "transactions.csv", parse_dates=["timestamp"])
    return acc, tx


class FeatureStore:
    """Running state of past transactions. ONE implementation used by both the
    batch builder (training) and the real-time API (serving), so there is no
    training/serving skew.

    features(tx) is read-only and uses only information strictly before tx.time.
    commit(tx)   adds a transaction to the state (call after the transfer happens).
    """

    def __init__(self, acc: pd.DataFrame):
        self.created = dict(zip(acc["account_id"], _seconds(acc["created_ts"])))
        self.rtype = dict(zip(acc["account_id"], acc["account_type"]))
        self.s_count = defaultdict(int)
        self.s_sum = defaultdict(float)
        self.s_recent = defaultdict(deque)       # (t, amount), sender's last hour
        self.s_devices = defaultdict(set)
        self.dev_senders = defaultdict(set)
        self.pair_count = defaultdict(int)
        self.r_recent = defaultdict(deque)       # (t, sender), incoming within 24h
        self.r_senders_all = defaultdict(set)
        self.r_in = defaultdict(int)
        self.r_out = defaultdict(int)
        self.r_cashout = defaultdict(int)
        self.s_incoming = defaultdict(deque)     # (t, from, amount), received within 3h
        self.last_ts = None

    def known(self, account_id: str) -> bool:
        return account_id in self.created

    def features(self, tx: dict, ts: pd.Timestamp) -> dict:
        t = (ts - EPOCH).total_seconds()
        s, r, a, dev = tx["sender_id"], tx["recipient_id"], float(tx["amount"]), tx["sender_device_id"]
        sr, rr, si = self.s_recent[s], self.r_recent[r], self.s_incoming[s]

        sr1h = [(tt, aa) for tt, aa in sr if t - tt <= H]
        last15 = [(tt, aa) for tt, aa in sr1h if t - tt <= 900]
        r24 = [(tt, snd) for tt, snd in rr if t - tt <= 24 * H]
        r1h = [snd for tt, snd in r24 if t - tt <= H]
        in3h = [(tt, frm, amt) for tt, frm, amt in si if t - tt <= 3 * H]
        tol = max(10.0, 0.02 * a)
        match = [frm for _, frm, amt in in3h if abs(amt - a) <= tol]
        n_prior = self.s_count[s]
        mean_prior = self.s_sum[s] / n_prior if n_prior else np.nan

        return dict(
            amount=a, log_amount=np.log1p(a), hour=ts.hour, is_night=int(ts.hour < 6),
            day_of_week=ts.dayofweek, is_month_end=int(ts.day >= 25 or ts.day <= 3),
            is_ussd=int(tx["channel"] == "ussd"), is_merchant_payment=int(tx["tx_type"] == "merchant_payment"),
            recipient_is_merchant=int(self.rtype.get(r) == "merchant"),
            recipient_is_agent=int(self.rtype.get(r) == "agent"),
            sender_age_h=(t - self.created[s]) / H, recipient_age_h=(t - self.created[r]) / H,
            sender_tx_count_prior=n_prior, sender_mean_amount_prior=mean_prior,
            amount_to_mean_ratio=a / mean_prior if n_prior else np.nan,
            sender_tx_15m=len(last15), sender_amount_15m=sum(aa for _, aa in last15),
            sender_tx_1h=len(sr1h),
            pair_count_prior=self.pair_count[(s, r)], is_new_recipient=int(self.pair_count[(s, r)] == 0),
            is_new_device=int(n_prior > 0 and dev not in self.s_devices[s]),
            device_shared_senders=len(self.dev_senders[dev] - {s}),
            recipient_senders_1h=len(set(r1h)), recipient_senders_24h=len({snd for _, snd in r24}),
            recipient_senders_all=len(self.r_senders_all[r]), recipient_in_count_1h=len(r1h),
            recipient_out_count_prior=self.r_out[r], recipient_in_out_ratio=self.r_in[r] / (self.r_out[r] + 1),
            recipient_cashout_prior=self.r_cashout[r],
            sender_received_3h=len(in3h), returning_recent_received=int(bool(match)),
            return_to_original_sender=int(r in match),
        )

    def commit(self, tx: dict, ts: pd.Timestamp) -> None:
        t = (ts - EPOCH).total_seconds()
        s, r, a, dev = tx["sender_id"], tx["recipient_id"], float(tx["amount"]), tx["sender_device_id"]
        sr, rr, si = self.s_recent[s], self.r_recent[r], self.s_incoming[s]
        while sr and t - sr[0][0] > H:           # prune old state (keeps memory bounded)
            sr.popleft()
        while rr and t - rr[0][0] > 24 * H:
            rr.popleft()
        while si and t - si[0][0] > 3 * H:
            si.popleft()
        self.s_count[s] += 1
        self.s_sum[s] += a
        sr.append((t, a))
        self.s_devices[s].add(dev)
        self.dev_senders[dev].add(s)
        self.pair_count[(s, r)] += 1
        rr.append((t, s))
        self.r_senders_all[r].add(s)
        self.r_in[r] += 1
        self.r_out[s] += 1
        if tx["tx_type"] == "cash_out":
            self.r_cashout[s] += 1
        self.s_incoming[r].append((t, s, a))
        self.last_ts = ts


def build_features(tx: pd.DataFrame, acc: pd.DataFrame) -> pd.DataFrame:
    """Batch builder: replays transactions in time order through the FeatureStore."""
    tx = tx.sort_values("timestamp", kind="stable").reset_index(drop=True)
    store = FeatureStore(acc)
    rows = []
    for x in tx.itertuples(index=False):
        d = x._asdict()
        rows.append(store.features(d, x.timestamp))
        store.commit(d, x.timestamp)
    feat = pd.DataFrame(rows)[FEATURES]
    meta = tx[["tx_id", "timestamp", "sender_id", "recipient_id", "tx_type", "is_scam", "scam_pattern"]].copy()
    meta["scorable"] = (~meta["scam_pattern"].isin(NOT_SCORED)).astype(int)
    return pd.concat([meta, feat], axis=1)


def time_split(feat: pd.DataFrame, train_end_day: int = 40, val_end_day: int = 50):
    """Chronological split: train < day 40 <= validation < day 50 <= test."""
    day = (feat["timestamp"] - feat["timestamp"].min().normalize()).dt.days
    return (feat[day < train_end_day],
            feat[(day >= train_end_day) & (day < val_end_day)],
            feat[day >= val_end_day])


def main():
    p = argparse.ArgumentParser(description="Build Safe-Send features")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="data/features.csv")
    args = p.parse_args()
    acc, tx = load(args.data)
    feat = build_features(tx, acc)
    feat.to_csv(args.out, index=False)
    tr, va, te = time_split(feat)
    for name, d in (("train", tr), ("val", va), ("test", te)):
        sc = d[d["scorable"] == 1]
        print(f"{name:5s} rows={len(sc):6d} scams={int(sc['is_scam'].sum()):4d} rate={sc['is_scam'].mean():.4f}")
    print(f"saved {len(feat)} rows x {len(FEATURES)} features -> {args.out}")


if __name__ == "__main__":
    main()
