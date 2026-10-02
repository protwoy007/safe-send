"""Adversarial ("evasive") scam generator used for the robustness stress test.

Models fraudsters who know a detector exists and adapt:
    mule rings   : rotate accounts (at most ~4 victims per mule), collect very slowly, use aged accounts
    splitting    : many small transfers (800-2,400 Tk) spread over hours, often from the victim's own device
    takeover     : modest amounts at normal hours, mostly from the victim's own device (SIM swap / remote access)
    return scams : always partial returns, to older compromised accounts
Everything else (normal behaviour, legitimate look-alikes) is unchanged.
"""
from __future__ import annotations

import numpy as np

from src.data_gen.generate import DAY, REGIONS, REGION_P, SyntheticMFS


class EvasiveMFS(SyntheticMFS):
    def mule_rings(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        for _ in range(c.n_mule_rings):
            t0 = self._sec(int(rng.integers(6, c.n_days - 2)))
            n_v = int(rng.integers(3, 31))
            n_m = max(1, int(np.ceil(n_v / 4)))
            span = rng.uniform(6, 48) * 3600
            mules = [self._new_mule(int(t0 - (rng.uniform(5, 60) if rng.random() < 0.6 else rng.uniform(0.3, 5)) * DAY))
                     for _ in range(n_m)]
            totals = {m: (0.0, t0) for m in mules}
            for k, v in enumerate(rng.choice(est, size=n_v, replace=False)):
                v, m = int(v), mules[k % n_m]
                sec = int(t0 + rng.uniform(0, span))
                amt = self.accounts[v]["baseline"] * rng.lognormal(0.2, 0.4) * (0.3 if rng.random() < 0.25 else 1.0)
                self._add(sec, v, m, amt, "send_money", self._device(v, sec), "mule", 1)
                tot, last = totals[m]
                totals[m] = (tot + self._amount(amt), max(last, sec))
            for m, (tot, last) in totals.items():
                self._cashout(m, int(last + rng.uniform(10 * 60, 90 * 60)), tot)

    def return_scams(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        pool = []
        for i in range(40):
            created = int(rng.integers(1, c.n_days - 6) * DAY)
            if rng.random() < 0.7:
                created = -int(rng.integers(30, 300)) * DAY      # older compromised accounts
            pool.append(self._acct("user", created, rng.choice(REGIONS, p=REGION_P), "scammer", device=f"DS{i:04d}"))
        self.scammers = pool
        for _ in range(c.n_return_scams):
            t0 = self._sec(int(rng.integers(6, c.n_days - 1)))
            live = [p for p in pool if self.accounts[p]["created_sec"] <= t0 - 3600]
            src, dst = (int(x) for x in rng.choice(live, size=2, replace=False))
            v = int(rng.choice(est))
            amt = self._amount(rng.uniform(2000, 8000))
            self._add(t0, src, v, amt, "send_money", self.accounts[src]["device"], "return_setup", 0)
            sec = int(t0 + rng.uniform(5 * 60, 90 * 60))
            self._add(sec, v, dst, amt * rng.uniform(0.5, 0.9), "send_money", self._device(v, sec), "return_scam", 1)

    def account_takeover(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        devices = [f"DVX{i:03d}" for i in range(20)]
        for _ in range(c.n_ato):
            v = int(rng.choice(est))
            sec = self._sec(int(rng.integers(3, c.n_days)))
            m = self._pick_mule(sec)
            amt = min(40_000, self.accounts[v]["baseline"] * rng.uniform(1.2, 2.5))
            dev = self._device(v, sec) if rng.random() < 0.8 else str(rng.choice(devices))
            self._add(sec, v, m, amt, "send_money", dev, "ato", 1, "app")
            self._cashout(m, int(sec + rng.uniform(10 * 60, 60 * 60)), self._amount(amt))

    def split_drain(self):
        c, rng = self.cfg, self.rng
        est = np.array(self.users_est)
        devices = [f"DVX{i:03d}" for i in range(20)]
        for _ in range(c.n_split):
            v = int(rng.choice(est))
            sec0 = self._sec(int(rng.integers(3, c.n_days)), int(rng.integers(8, 20)))
            m = self._pick_mule(sec0)
            dev = self._device(v, sec0) if rng.random() < 0.7 else str(rng.choice(devices))
            total = 0
            for _ in range(int(rng.integers(8, 16))):
                sec = int(sec0 + rng.uniform(0, 5 * 3600))
                amt = rng.uniform(800, 2400)
                self._add(sec, v, m, amt, "send_money", dev, "split", 1, "app")
                total += self._amount(amt)
            self._cashout(m, int(sec0 + 6 * 3600), total)
