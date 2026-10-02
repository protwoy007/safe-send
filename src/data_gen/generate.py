"""Synthetic MFS transaction generator for Safe-Send.

Produces a fully synthetic wallet network with normal behaviour, legitimate
look-alikes (so the model cannot learn trivial shortcuts) and injected scam
patterns. No real personal data is used anywhere.

Outputs (in --out directory):
    accounts.csv      one row per wallet. Columns prefixed `gt_` are ground
                      truth for evaluation only and MUST NOT be model features.
    transactions.csv  one row per transfer, sorted by time.
    summary.json      counts and scam rates per pattern.

Label definition:
    is_scam = 1 only for transfers a *sender* is tricked or forced into
    (the transfers Safe-Send would intercept). Post-event mule cash-outs are
    included for graph/velocity features but are labelled 0
    (scam_pattern = "mule_cashout").

Usage:
    python -m src.data_gen.generate --out data --seed 42
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DAY = 86_400
REGIONS = ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet", "Barishal", "Rangpur"]
REGION_P = [0.38, 0.17, 0.10, 0.10, 0.08, 0.07, 0.10]
RULE_THRESHOLD = 5_000  # static-rule amount limit; split pattern stays below it
MAX_AMOUNT = 45_000


@dataclass
class Config:
    seed: int = 42
    start: str = "2026-07-01"
    n_days: int = 60
    n_users: int = 3000
    n_merchants: int = 150
    n_new_merchants: int = 12
    n_agents: int = 30
    n_mule_rings: int = 30
    n_return_scams: int = 120
    n_ato: int = 90
    n_split: int = 30
    n_legit_returns: int = 150
    n_legit_fanin: int = 25
    n_legit_newdev: int = 60


class SyntheticMFS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.accounts: list[dict] = []
        self.tx: list[dict] = []
        self.users_est: list[int] = []
        self.users_new: list[int] = []
        self.merchants: list[int] = []
        self.new_merchants: list[int] = []
        self.agents: list[int] = []
        self.mules: list[int] = []
        self.scammers: list[int] = []
        h = np.arange(24)
        w = np.exp(-(((h - 15) / 5.5) ** 2)) + 0.05
        self.hour_w = w / w.sum()

    # ---------- helpers ----------
    def _acct(self, atype, created, region, role, baseline=None, band=None, device=None, switch=-1):
        idx = len(self.accounts)
        self.accounts.append(dict(
            idx=idx, account_type=atype, created_sec=int(created), region=region,
            gt_role=role, baseline=baseline, value_band=band, device=device, switch_day=switch,
        ))
        return idx

    def _device(self, idx, sec):
        a = self.accounts[idx]
        if a["switch_day"] >= 0 and sec >= a["switch_day"] * DAY:
            return a["device"] + "b"
        return a["device"]

    @staticmethod
    def _amount(x):
        return int(min(MAX_AMOUNT, max(10, round(float(x) / 10) * 10)))

    def _add(self, sec, s, r, amount, ttype, device, pattern, label, channel=None):
        if channel is None:
            channel = "ussd" if self.rng.random() < 0.2 else "app"
        self.tx.append(dict(
            sec=int(sec), sender=s, recipient=r, amount=self._amount(amount), tx_type=ttype,
            sender_device_id=device, channel=channel, is_scam=int(label), scam_pattern=pattern,
        ))

    def _sec(self, day, hour=None):
        h = int(self.rng.choice(24, p=self.hour_w)) if hour is None else hour
        return int(day * DAY + h * 3600 + self.rng.integers(0, 3600))

    def _horizon(self):
        return self.cfg.n_days * DAY - 1

    # ---------- accounts ----------
    def build_accounts(self):
        c, rng = self.cfg, self.rng
        for i in range(c.n_users):
            new = rng.random() < 0.12
            if new:
                created = int(rng.integers(0, c.n_days - 3) * DAY + rng.integers(0, DAY))
            else:
                created = -int(rng.integers(30, 1500)) * DAY
            base = float(np.clip(rng.lognormal(np.log(1000), 0.8), 100, 8000))
            band = "low" if base < 500 else ("high" if base > 2500 else "mid")
            switch = int(rng.integers(10, c.n_days)) if rng.random() < 0.02 else -1
            idx = self._acct("user", created, rng.choice(REGIONS, p=REGION_P), "normal",
                             base, band, f"DV{i:05d}", switch)
            (self.users_new if new else self.users_est).append(idx)
        for i in range(c.n_merchants):
            self.merchants.append(self._acct(
                "merchant", -int(rng.integers(100, 1500)) * DAY,
                rng.choice(REGIONS, p=REGION_P), "normal", device=f"MD{i:04d}"))
        for i in range(c.n_new_merchants):
            created = int(rng.integers(5, c.n_days - 2) * DAY + 9 * 3600)
            self.new_merchants.append(self._acct(
                "merchant", created, rng.choice(REGIONS, p=REGION_P), "normal", device=f"MN{i:04d}"))
        for i in range(c.n_agents):
            self.agents.append(self._acct(
                "agent", -int(rng.integers(100, 1500)) * DAY,
                rng.choice(REGIONS, p=REGION_P), "normal", device=f"AG{i:04d}"))
        self.contacts = {}
        est = np.array(self.users_est)
        for u in self.users_est + self.users_new:
            k = int(rng.integers(3, 9))
            pool = est[est != u]
            self.contacts[u] = rng.choice(pool, size=k, replace=False)

    # ---------- legitimate behaviour ----------
    def normal_activity(self):
        c, rng = self.cfg, self.rng
        dates = pd.date_range(c.start, periods=c.n_days)
        day_w = np.where((dates.day >= 25) | (dates.day <= 3), 1.35, 1.0)
        day_w = day_w * np.where(dates.dayofweek.isin([4, 5]), 1.15, 1.0)
        mw = 1.0 / np.arange(1, len(self.merchants) + 1) ** 0.8
        mw = mw / mw.sum()
        est = np.array(self.users_est)
        for u in self.users_est + self.users_new:
            a = self.accounts[u]
            created = a["created_sec"]
            start_day = max(0, created // DAY)
            n = rng.poisson(rng.uniform(0.25, 0.6) * (c.n_days - start_day))
            if n == 0:
                continue
            w = day_w[start_day:]
            days = rng.choice(np.arange(start_day, c.n_days), size=n, p=w / w.sum())
            for d in days:
                sec = self._sec(d)
                if sec < created + 3600:
                    continue
                r, base = rng.random(), a["baseline"]
                pattern, ttype = "normal", "send_money"
                if r < 0.78:
                    rec = int(rng.choice(self.contacts[u]))
                    amt = base * rng.lognormal(0, 0.45)
                    if rng.random() < 0.012:  # rent, tuition, family support
                        amt, pattern = base * rng.uniform(3, 8), "legit_large"
                elif r < 0.92:
                    rec = int(rng.choice(self.merchants, p=mw))
                    amt, ttype = base * 0.35 * rng.lognormal(0, 0.5), "merchant_payment"
                else:
                    rec = int(rng.choice(est[est != u]))
                    amt = base * 0.8 * rng.lognormal(0, 0.5)
                self._add(sec, u, rec, amt, ttype, self._device(u, sec), pattern, 0)

    def legit_lookalikes(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        # relatives funding a brand-new wallet (legit new account receiving money)
        for u in self.users_new:
            created = self.accounts[u]["created_sec"]
            for s in rng.choice(est, size=int(rng.integers(1, 4)), replace=False):
                sec = int(created + rng.uniform(0.1 * 3600, 5 * DAY))
                if sec < self._horizon():
                    self._add(sec, int(s), u, rng.uniform(500, 5000), "send_money",
                              self._device(int(s), sec), "legit_welcome", 0)
        # opening-day promotions: many senders into a new merchant (legit fan-in)
        for m in self.new_merchants:
            created = self.accounts[m]["created_sec"]
            for s in rng.choice(est, size=int(rng.integers(15, 40)), replace=False):
                sec = int(created + rng.uniform(0, 3 * 3600))
                self._add(sec, int(s), m, rng.uniform(50, 500), "merchant_payment",
                          self._device(int(s), sec), "legit_new_merchant_burst", 0)
        # genuine mistaken transfers returned to the ORIGINAL sender (known counterparty)
        for _ in range(c.n_legit_returns):
            x = int(rng.choice(est))
            y = int(rng.choice(self.contacts[x]))
            sec = self._sec(int(rng.integers(1, c.n_days - 1)))
            amt = self._amount(rng.uniform(500, 5000))
            self._add(sec, x, y, amt, "send_money", self._device(x, sec), "normal", 0)
            back = int(sec + rng.uniform(10 * 60, 3 * 3600))
            self._add(back, y, x, amt, "send_money", self._device(y, back), "legit_return", 0)

    def hard_lookalikes(self):
        """Legit cases that mimic scam signals so classes overlap (as in real life)."""
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        # a new wallet legitimately receiving from many people (fundraiser, small seller)
        pick = rng.choice(self.users_new, size=min(c.n_legit_fanin, len(self.users_new)), replace=False)
        for u in pick:
            u = int(u)
            t0 = self.accounts[u]["created_sec"] + rng.uniform(0.5, 5) * DAY
            span = rng.uniform(1, 12) * 3600
            for s in rng.choice(est, size=int(rng.integers(8, 21)), replace=False):
                sec = int(t0 + rng.uniform(0, span))
                self._add(sec, int(s), u, rng.uniform(100, 2000), "send_money",
                          self._device(int(s), sec), "legit_fanin", 0)
        # large transfer from a new device (new phone, travelling) to a known contact
        for _ in range(c.n_legit_newdev):
            x = int(rng.choice(est))
            y = int(rng.choice(self.contacts[x]))
            sec = self._sec(int(rng.integers(3, c.n_days)), int(rng.integers(8, 20)))
            self._add(sec, x, y, self.accounts[x]["baseline"] * rng.uniform(3, 8), "send_money",
                      self.accounts[x]["device"] + "n", "legit_new_device_large", 0)

    # ---------- scam patterns ----------
    def _cashout(self, mule, sec, amount):
        agent = int(self.rng.choice(self.agents))
        self._add(sec, mule, agent, amount * 0.97, "cash_out",
                  self.accounts[mule]["device"], "mule_cashout", 0)

    def _new_mule(self, created):
        m = self._acct("user", created, self.rng.choice(REGIONS, p=REGION_P), "mule",
                       device=f"DM{len(self.mules):04d}")
        self.mules.append(m)
        return m

    def mule_rings(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        for _ in range(c.n_mule_rings):
            t0 = self._sec(int(rng.integers(6, c.n_days - 2)))
            aged = rng.random() < 0.3                 # some mules are aged / dormant accounts
            span = rng.uniform(0.5, 24) * 3600        # slow rings are harder to spot
            mules = [self._new_mule(int(t0 - (rng.uniform(5, 40) if aged else rng.uniform(0.3, 5)) * DAY))
                     for _ in range(int(rng.integers(1, 4)))]
            totals = {m: (0.0, t0) for m in mules}
            for v in rng.choice(est, size=int(rng.integers(3, 31)), replace=False):
                v, m = int(v), int(rng.choice(mules))
                sec = int(t0 + rng.uniform(0, span))
                amt = self.accounts[v]["baseline"] * rng.lognormal(0.2, 0.4) * (0.3 if rng.random() < 0.25 else 1.0)
                self._add(sec, v, m, amt, "send_money", self._device(v, sec), "mule", 1)
                tot, last = totals[m]
                totals[m] = (tot + self._amount(amt), max(last, sec))
            for m, (tot, last) in totals.items():
                self._cashout(m, int(last + rng.uniform(10 * 60, 90 * 60)), tot)

    def _pick_mule(self, sec):
        live = [m for m in self.mules if self.accounts[m]["created_sec"] <= sec - 3600]
        return int(self.rng.choice(live)) if live else self._new_mule(sec - DAY)

    def return_scams(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        pool = []
        for i in range(40):
            created = int((rng.integers(1, 5) if i < 8 else rng.integers(1, c.n_days - 6)) * DAY)
            if i >= 8 and rng.random() < 0.25:        # compromised older account
                created = -int(rng.integers(10, 200)) * DAY
            pool.append(self._acct("user", created, rng.choice(REGIONS, p=REGION_P),
                                   "scammer", device=f"DS{i:04d}"))
        self.scammers = pool
        for _ in range(c.n_return_scams):
            t0 = self._sec(int(rng.integers(6, c.n_days - 1)))
            live = [p for p in pool if self.accounts[p]["created_sec"] <= t0 - 3600]
            src, dst = (int(x) for x in rng.choice(live, size=2, replace=False))
            v = int(rng.choice(est))
            amt = self._amount(rng.uniform(2000, 8000))
            self._add(t0, src, v, amt, "send_money", self.accounts[src]["device"], "return_setup", 0)
            sec = int(t0 + rng.uniform(5 * 60, 90 * 60))
            back = amt if rng.random() < 0.6 else amt * rng.uniform(0.6, 0.95)   # partial returns
            self._add(sec, v, dst, back, "send_money", self._device(v, sec), "return_scam", 1)

    def account_takeover(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        devices = [f"DVX{i:03d}" for i in range(20)]  # attacker devices reused across victims
        for _ in range(c.n_ato):
            v = int(rng.choice(est))
            hour = int(rng.integers(1, 6)) if rng.random() < 0.4 else int(rng.choice(24, p=self.hour_w))
            sec = self._sec(int(rng.integers(3, c.n_days)), hour)
            m = self._pick_mule(sec)
            mult = rng.uniform(4, 12) if rng.random() < 0.5 else rng.uniform(1.2, 3.5)
            amt = min(40_000, self.accounts[v]["baseline"] * mult)
            dev = self._device(v, sec) if rng.random() < 0.35 else str(rng.choice(devices))  # SIM swap / remote access
            self._add(sec, v, m, amt, "send_money", dev, "ato", 1, "app")
            self._cashout(m, int(sec + rng.uniform(10 * 60, 60 * 60)), self._amount(amt))

    def split_drain(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        devices = [f"DVX{i:03d}" for i in range(20)]
        for _ in range(c.n_split):
            v = int(rng.choice(est))
            sec0 = self._sec(int(rng.integers(3, c.n_days)), int(rng.integers(1, 6)))
            m = self._pick_mule(sec0)
            dev = self._device(v, sec0) if rng.random() < 0.4 else str(rng.choice(devices))
            total = 0
            for _ in range(int(rng.integers(5, 9))):
                sec = int(sec0 + rng.uniform(0, 20 * 60))
                amt = rng.uniform(2500, RULE_THRESHOLD - 500)
                self._add(sec, v, m, amt, "send_money", dev, "split", 1, "app")
                total += self._amount(amt)
            self._cashout(m, int(sec0 + 40 * 60), total)

    # ---------- assemble ----------
    def build(self):
        self.build_accounts()
        self.normal_activity()
        self.legit_lookalikes()
        self.hard_lookalikes()
        self.mule_rings()
        self.return_scams()
        self.account_takeover()
        self.split_drain()
        return self._frames()

    def _frames(self):
        rng, start = self.rng, pd.Timestamp(self.cfg.start)
        ids = {i: f"AC{100000 + int(p)}" for i, p in enumerate(rng.permutation(len(self.accounts)))}
        acc = pd.DataFrame(self.accounts)
        acc["account_id"] = acc["idx"].map(ids)
        acc["created_ts"] = start + pd.to_timedelta(acc["created_sec"], unit="s")
        acc = acc[["account_id", "account_type", "created_ts", "region", "value_band", "gt_role"]]
        acc = acc.sort_values("account_id").reset_index(drop=True)

        tx = pd.DataFrame(self.tx)
        tx = tx[tx["sec"] <= self._horizon()].sort_values("sec", kind="stable").reset_index(drop=True)
        tx["timestamp"] = start + pd.to_timedelta(tx["sec"], unit="s")
        tx["sender_id"] = tx["sender"].map(ids)
        tx["recipient_id"] = tx["recipient"].map(ids)
        tx.insert(0, "tx_id", [f"TX{i:06d}" for i in range(1, len(tx) + 1)])
        tx = tx[["tx_id", "timestamp", "sender_id", "recipient_id", "amount", "tx_type",
                 "sender_device_id", "channel", "is_scam", "scam_pattern"]]
        return acc, tx


def summarize(acc: pd.DataFrame, tx: pd.DataFrame) -> dict:
    return {
        "n_accounts": int(len(acc)),
        "n_transactions": int(len(tx)),
        "scam_rate": round(float(tx["is_scam"].mean()), 5),
        "n_scam_transactions": int(tx["is_scam"].sum()),
        "transactions_by_pattern": tx["scam_pattern"].value_counts().to_dict(),
        "accounts_by_role": acc["gt_role"].value_counts().to_dict(),
        "period": [str(tx["timestamp"].min()), str(tx["timestamp"].max())],
    }


def main():
    p = argparse.ArgumentParser(description="Generate synthetic Safe-Send data")
    p.add_argument("--out", default="data")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--users", type=int, default=3000)
    args = p.parse_args()
    acc, tx = SyntheticMFS(Config(seed=args.seed, n_users=args.users)).build()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    acc.to_csv(out / "accounts.csv", index=False)
    tx.to_csv(out / "transactions.csv", index=False)
    summary = summarize(acc, tx)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
