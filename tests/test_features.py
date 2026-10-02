import numpy as np
import pytest

from src.data_gen.generate import Config, SyntheticMFS
from src.features.build import FEATURES, build_features, time_split


@pytest.fixture(scope="module")
def built():
    acc, tx = SyntheticMFS(Config(seed=11, n_users=600)).build()
    return acc, tx, build_features(tx, acc)


def test_columns_and_no_ground_truth_in_features(built):
    _, _, feat = built
    assert set(FEATURES) <= set(feat.columns)
    assert not any(c.startswith("gt_") or c in ("is_scam", "scam_pattern") for c in FEATURES)


def test_no_future_leakage(built):
    """Features of row i must be identical when only rows 0..i are available."""
    acc, tx, feat = built
    tx = tx.sort_values("timestamp", kind="stable").reset_index(drop=True)
    n = len(tx)
    for i in (500, n // 3, n // 2, n - 1):
        prefix = build_features(tx.iloc[: i + 1], acc).iloc[-1][FEATURES].astype(float).to_numpy()
        full = feat.iloc[i][FEATURES].astype(float).to_numpy()
        assert np.allclose(prefix, full, equal_nan=True), f"leakage at row {i}"


def test_return_cue_separates_scam_from_legit_return(built):
    _, _, feat = built
    scam = feat[feat["scam_pattern"] == "return_scam"]
    legit = feat[feat["scam_pattern"] == "legit_return"]
    assert scam["returning_recent_received"].mean() > 0.4
    assert (scam["return_to_original_sender"] == 0).all()
    assert (legit["return_to_original_sender"] == 1).all()


def test_time_split_is_chronological(built):
    _, _, feat = built
    tr, va, te = time_split(feat)
    assert tr["timestamp"].max() < va["timestamp"].min()
    assert va["timestamp"].max() < te["timestamp"].min()
    assert len(tr) + len(va) + len(te) == len(feat)
    assert te["is_scam"].sum() > 0
