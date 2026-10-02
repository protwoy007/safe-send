"""Train and evaluate the Safe-Send risk model against a static-rule baseline.

Steps
    1. Load features, keep scorable rows, chronological train/val/test split.
    2. Baseline: static rules (amount limit + blacklist built from TRAIN labels only).
    3. LightGBM risk score, early-stopped on the validation set.
    4. Tier thresholds chosen on VALIDATION (by false-positive budget), never on test.
    5. One final evaluation on TEST: ranking metrics, tiers, per-pattern recall,
       amount-splitting stress result, false-positive rates by group.

Outputs: models/risk_model.pkl, models/thresholds.json, reports/metrics.json

Usage:
    python -m src.models.train --data data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from src.features.build import FEATURES, load, time_split

RULE_AMOUNT_LIMIT = 5_000      # static-rule amount limit
FPR_BUDGET = {"medium": 0.015, "high": 0.004, "extreme": 0.001}  # share of legit transfers


# ---------------------------------------------------------------- baseline
def rule_baseline(df: pd.DataFrame, blacklist: set[str]) -> np.ndarray:
    """Static rules: amount at/above the limit OR recipient on the blacklist."""
    return ((df["amount"] >= RULE_AMOUNT_LIMIT) | df["recipient_id"].isin(blacklist)).astype(int).to_numpy()


# ---------------------------------------------------------------- helpers
def fpr_threshold(scores: np.ndarray, y: np.ndarray, fpr: float) -> float:
    """Smallest threshold whose false-positive rate on legit transfers is <= fpr."""
    return float(np.quantile(scores[y == 0], 1 - fpr))


def recall_precision(flag: np.ndarray, y: np.ndarray) -> dict:
    tp = int(((flag == 1) & (y == 1)).sum())
    fp = int(((flag == 1) & (y == 0)).sum())
    return {
        "flag_rate": round(float(flag.mean()), 4),
        "recall": round(tp / max(1, int(y.sum())), 4),
        "precision": round(tp / max(1, tp + fp), 4),
        "false_positive_rate": round(fp / max(1, int((y == 0).sum())), 4),
    }


def top_k(scores: np.ndarray, y: np.ndarray, frac: float) -> dict:
    k = max(1, int(len(y) * frac))
    idx = np.argsort(-scores)[:k]
    tp = int(y[idx].sum())
    return {"k": k, "precision": round(tp / k, 4), "recall": round(tp / max(1, int(y.sum())), 4)}


def tier(scores: np.ndarray, thr: dict) -> np.ndarray:
    out = np.zeros(len(scores), dtype=int)  # 0 low, 1 medium, 2 high, 3 extreme
    out[scores >= thr["medium"]] = 1
    out[scores >= thr["high"]] = 2
    out[scores >= thr["extreme"]] = 3
    return out


# ---------------------------------------------------------------- main
def run(data_dir: str = "data", model_dir: str = "models", report_dir: str = "reports") -> dict:
    acc, tx = load(data_dir)
    feat = pd.read_csv(Path(data_dir) / "features.csv", parse_dates=["timestamp"])
    feat = feat[feat["scorable"] == 1].reset_index(drop=True)
    tr, va, te = time_split(feat)

    blacklist = set(tr.loc[tr["is_scam"] == 1, "recipient_id"])  # known-bad recipients from training period only

    # --- model
    params = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_child_samples=20,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, reg_lambda=1.0,
                  scale_pos_weight=5.0, verbose=-1, seed=42)
    dtr = lgb.Dataset(tr[FEATURES], tr["is_scam"])
    dva = lgb.Dataset(va[FEATURES], va["is_scam"], reference=dtr)
    booster = lgb.train(params, dtr, num_boost_round=600, valid_sets=[dva],
                        callbacks=[lgb.early_stopping(40, verbose=False)])

    s_va = booster.predict(va[FEATURES], num_iteration=booster.best_iteration)
    s_te = booster.predict(te[FEATURES], num_iteration=booster.best_iteration)
    y_va, y_te = va["is_scam"].to_numpy(), te["is_scam"].to_numpy()

    # --- tier thresholds from VALIDATION only
    thr = {k: fpr_threshold(s_va, y_va, v) for k, v in FPR_BUDGET.items()}

    # --- baseline on test
    base_flag = rule_baseline(te, blacklist)
    base = recall_precision(base_flag, y_te)
    # model at the SAME alert volume as the baseline (fair comparison)
    same_vol_thr = float(np.quantile(s_te, 1 - base_flag.mean()))
    model_same_volume = recall_precision((s_te >= same_vol_thr).astype(int), y_te)

    # --- model at the medium tier (warn threshold)
    t = tier(s_te, thr)
    warn = (t >= 1).astype(int)

    tiers = {}
    for name, level in (("low", 0), ("medium", 1), ("high", 2), ("extreme", 3)):
        m = t == level
        tiers[name] = {
            "share_of_all_transfers": round(float(m.mean()), 4),
            "scam_transfers": int(y_te[m].sum()),
            "legit_transfers": int((1 - y_te[m]).sum()),
        }

    # --- per-pattern recall (warn = medium or above), incl. amount-splitting stress
    pat = te["scam_pattern"].to_numpy()
    per_pattern = {}
    for p in ("mule", "return_scam", "ato", "split"):
        m = pat == p
        per_pattern[p] = {
            "n": int(m.sum()),
            "model_recall": round(float(warn[m].mean()), 4) if m.any() else None,
            "rule_baseline_recall": round(float(base_flag[m].mean()), 4) if m.any() else None,
        }

    # --- fairness: false-positive rate on LEGIT transfers by group (warn threshold)
    meta = acc.set_index("account_id")
    te = te.assign(
        warn=warn,
        region=te["sender_id"].map(meta["region"]),
        value_band=te["sender_id"].map(meta["value_band"]),
        sender_group=np.where(te["sender_age_h"] < 30 * 24, "new_account(<30d)", "established"),
    )
    legit = te[te["is_scam"] == 0]
    fairness = {
        col: {str(k): round(float(v), 4) for k, v in legit.groupby(col)["warn"].mean().items()}
        for col in ("value_band", "sender_group", "region")
    }

    importance = dict(sorted(
        zip(FEATURES, booster.feature_importance(importance_type="gain").round(1).tolist()),
        key=lambda kv: -kv[1]))

    metrics = {
        "split_sizes": {"train": len(tr), "val": len(va), "test": len(te)},
        "best_iteration": int(booster.best_iteration),
        "test": {
            "pr_auc": round(float(average_precision_score(y_te, s_te)), 4),
            "roc_auc": round(float(roc_auc_score(y_te, s_te)), 4),
            "top_1pct": top_k(s_te, y_te, 0.01),
            "top_2pct": top_k(s_te, y_te, 0.02),
            "scam_base_rate": round(float(y_te.mean()), 4),
        },
        "rule_baseline_test": base,
        "model_at_same_alert_volume": model_same_volume,
        "model_warn_threshold_test": recall_precision(warn, y_te),
        "tiers_test": tiers,
        "per_pattern_recall": per_pattern,
        "false_positive_rate_by_group": fairness,
        "feature_importance_gain": importance,
        "thresholds": thr,
    }

    Path(model_dir).mkdir(exist_ok=True)
    Path(report_dir).mkdir(exist_ok=True)
    joblib.dump({"booster": booster, "features": FEATURES, "thresholds": thr,
                 "blacklist": sorted(blacklist)}, Path(model_dir) / "risk_model.pkl")
    (Path(model_dir) / "thresholds.json").write_text(json.dumps(thr, indent=2))
    (Path(report_dir) / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    args = p.parse_args()
    m = run(args.data)
    t = m["test"]
    print(f"TEST  PR-AUC={t['pr_auc']}  ROC-AUC={t['roc_auc']}  base_rate={t['scam_base_rate']}")
    print(f"      top-1% precision={t['top_1pct']['precision']} recall={t['top_1pct']['recall']}")
    print(f"RULES        {m['rule_baseline_test']}")
    print(f"MODEL (same alert volume) {m['model_at_same_alert_volume']}")
    print(f"MODEL warn   {m['model_warn_threshold_test']}")
    print("PER PATTERN  ", json.dumps(m["per_pattern_recall"]))
    print("FPR BY GROUP ", json.dumps(m["false_positive_rate_by_group"]))
    print("TIERS        ", json.dumps(m["tiers_test"]))
    print("saved models/risk_model.pkl, models/thresholds.json, reports/metrics.json")


if __name__ == "__main__":
    main()
