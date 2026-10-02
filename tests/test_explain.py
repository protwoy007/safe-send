import lightgbm as lgb
import pandas as pd
import pytest

from src.data_gen.generate import Config, SyntheticMFS
from src.explain.reasons import ACTIONS, FEATURE_TO_GROUP, Explainer
from src.features.build import FEATURES, build_features


@pytest.fixture(scope="module")
def setup():
    acc, tx = SyntheticMFS(Config(seed=5, n_users=600)).build()
    feat = build_features(tx, acc)
    feat = feat[feat["scorable"] == 1].reset_index(drop=True)
    booster = lgb.train(
        dict(objective="binary", learning_rate=0.1, num_leaves=15, verbose=-1, seed=1),
        lgb.Dataset(feat[FEATURES], feat["is_scam"]), num_boost_round=80)
    thr = {"medium": 0.3, "high": 0.6, "extreme": 0.9}
    return Explainer(booster, thr), feat


def test_every_feature_group_is_known():
    assert all(g for g in FEATURE_TO_GROUP.values())


def test_structure_and_tiers(setup):
    ex, feat = setup
    res = ex.explain(feat.sample(30, random_state=0))
    assert len(res) == 30
    for r in res:
        assert r["tier"] in ("low", "medium", "high", "extreme")
        assert r["action_message"] == ACTIONS["en"][r["tier"]]
        assert len(r["reasons"]) <= 3
        if r["tier"] == "low":
            assert r["reasons"] == []
        assert all(x["impact"] >= 0.10 and x["text"] for x in r["reasons"])


def test_return_scam_gets_return_reason_and_bangla(setup):
    ex, feat = setup
    sc = feat[(feat["scam_pattern"] == "return_scam") & (feat["returning_recent_received"] == 1)].head(10)
    en = ex.explain(sc, "en")
    bn = ex.explain(sc, "bn")
    assert any(x["code"] == "RETURN" for r in en for x in r["reasons"])
    assert all(r["action_message"] == ACTIONS["bn"][r["tier"]] for r in bn)
    assert any(any("\u0980" <= ch <= "\u09FF" for ch in x["text"]) for r in bn for x in r["reasons"])


def test_reason_text_matches_data(setup):
    """A reason is only shown when its condition really holds in the row."""
    ex, feat = setup
    rows = feat[feat["is_scam"] == 1].head(60)
    for i, res in enumerate(ex.explain(rows)):
        row = rows.iloc[i]
        for x in res["reasons"]:
            if x["code"] == "RETURN":
                assert row["returning_recent_received"] == 1 and row["return_to_original_sender"] == 0
            if x["code"] == "NEW_ACCOUNT":
                assert row["recipient_age_h"] <= 14 * 24
            if x["code"] == "DEVICE":
                assert row["is_new_device"] == 1 or row["device_shared_senders"] >= 1
