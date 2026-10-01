import pandas as pd
import pytest

from src.data_gen.generate import Config, SyntheticMFS


@pytest.fixture(scope="module")
def data():
    return SyntheticMFS(Config(seed=7)).build()


def test_schema(data):
    acc, tx = data
    assert {"tx_id", "timestamp", "sender_id", "recipient_id", "amount", "tx_type",
            "sender_device_id", "channel", "is_scam", "scam_pattern"} <= set(tx.columns)
    assert {"account_id", "account_type", "created_ts", "region", "value_band", "gt_role"} <= set(acc.columns)


def test_sorted_unique_positive(data):
    _, tx = data
    assert tx["timestamp"].is_monotonic_increasing
    assert tx["tx_id"].is_unique
    assert (tx["amount"] > 0).all()
    assert (tx["sender_id"] != tx["recipient_id"]).all()


def test_scam_rate_reasonable(data):
    _, tx = data
    assert 0.005 < tx["is_scam"].mean() < 0.03


def test_all_patterns_present(data):
    _, tx = data
    scam = set(tx.loc[tx["is_scam"] == 1, "scam_pattern"])
    assert scam == {"mule", "return_scam", "ato", "split"}


def test_accounts_exist_before_use(data):
    acc, tx = data
    created = acc.set_index("account_id")["created_ts"]
    assert (tx["timestamp"] >= tx["sender_id"].map(created)).all()
    assert (tx["timestamp"] >= tx["recipient_id"].map(created)).all()


def test_split_stays_under_rule_threshold(data):
    _, tx = data
    assert tx.loc[tx["scam_pattern"] == "split", "amount"].max() < 5_000


def test_deterministic():
    a1, t1 = SyntheticMFS(Config(seed=3, n_users=300)).build()
    a2, t2 = SyntheticMFS(Config(seed=3, n_users=300)).build()
    pd.testing.assert_frame_equal(t1, t2)
