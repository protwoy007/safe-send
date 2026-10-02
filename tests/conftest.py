import joblib
import lightgbm as lgb
import pytest

from src.data_gen.generate import Config, SyntheticMFS
from src.features.build import FEATURES, build_features


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    """Small synthetic world + quick model, shared by API and network tests."""
    d = tmp_path_factory.mktemp("data")
    acc, tx = SyntheticMFS(Config(seed=9, n_users=600)).build()
    acc.to_csv(d / "accounts.csv", index=False)
    tx.to_csv(d / "transactions.csv", index=False)
    feat = build_features(tx, acc)
    feat.to_csv(d / "features.csv", index=False)
    sc = feat[feat["scorable"] == 1]
    booster = lgb.train(dict(objective="binary", learning_rate=0.1, num_leaves=15, verbose=-1, seed=1),
                        lgb.Dataset(sc[FEATURES], sc["is_scam"]), num_boost_round=80)
    thr = {"medium": 0.3, "high": 0.6, "extreme": 0.9}
    joblib.dump({"booster": booster, "features": FEATURES, "thresholds": thr, "blacklist": []}, d / "m.pkl")
    return d
