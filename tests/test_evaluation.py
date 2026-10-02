import numpy as np
import pandas as pd

from src.data_gen.generate import Config
from src.evaluation.evasion import EvasiveMFS
from src.evaluation.report import final_tiers, simulate, wilson
from src.rules.policy import LARGE_AMOUNT_LIMIT


def test_wilson_interval_sane():
    lo, hi = wilson(95, 100)
    assert 0.88 < lo < 0.95 < hi < 0.99
    assert wilson(0, 0) == (0.0, 0.0)
    assert wilson(10, 10)[1] == 1.0


def test_large_amount_rule_raises_tier_only():
    df = pd.DataFrame({"amount": [100.0, LARGE_AMOUNT_LIMIT + 1, LARGE_AMOUNT_LIMIT + 1]})
    scores = np.array([0.0, 0.0, 0.99])
    t = final_tiers(scores, df, {"medium": 0.3, "high": 0.6, "extreme": 0.9})
    assert list(t) == [0, 2, 3]


def test_simulation_monotonic_and_hold_only_is_lower():
    df = pd.DataFrame({"is_scam": [1, 1, 0, 0], "amount": [1000.0, 2000.0, 500.0, 800.0]})
    tiers = np.array([2, 3, 1, 0])
    base, half = simulate(df, tiers), simulate(df, tiers, mult=0.5)
    hold = simulate(df, tiers, hold_only=True)
    assert half["loss_prevented_tk"] < base["loss_prevented_tk"]
    assert hold["loss_prevented_tk"] <= base["loss_prevented_tk"]
    assert hold["legit_value_abandoned_tk"] == 0


def test_evasive_generator_produces_all_patterns():
    _, tx = EvasiveMFS(Config(seed=3, n_users=500, n_mule_rings=10, n_return_scams=20, n_ato=15, n_split=8)).build()
    assert set(tx.loc[tx["is_scam"] == 1, "scam_pattern"]) == {"mule", "return_scam", "ato", "split"}
    assert tx.loc[tx["scam_pattern"] == "split", "amount"].max() <= 2400
