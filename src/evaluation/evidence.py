"""Model evidence pack: feature ablation, calibration, cost-based threshold, simpler baseline.

Answers four questions a reviewer should ask:
  1. Does the model depend on one shortcut feature? (ablation, incl. without recipient account age)
  2. Are the scores calibrated? (reliability table, ECE, isotonic calibration on validation)
  3. Which threshold minimises expected cost? (cost-based choice vs false-positive budget)
  4. Is a simple linear model enough? (logistic regression baseline)

All results are on synthetic data (chronological split, test used once).

Usage:  python -m src.evaluation.evidence --data data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from src.features.build import FEATURES, time_split  # noqa: E402
from src.models.train import FPR_BUDGET, PARAMS, fpr_threshold  # noqa: E402

NETWORK = ["recipient_senders_1h", "recipient_senders_24h", "recipient_senders_all", "recipient_in_count_1h",
           "recipient_in_out_ratio", "recipient_out_count_prior", "recipient_cashout_prior", "device_shared_senders"]
RETURN_CUES = ["sender_received_3h", "returning_recent_received", "return_to_original_sender"]
SENDER_BEHAVIOR = ["amount_to_mean_ratio", "sender_mean_amount_prior", "sender_tx_count_prior", "sender_tx_15m",
                   "sender_amount_15m", "sender_tx_1h", "pair_count_prior", "is_new_recipient", "is_new_device"]
ABLATIONS = {
    "full model": [],
    "without recipient account age": ["recipient_age_h"],
    "without both account ages": ["recipient_age_h", "sender_age_h"],
    "without network features": NETWORK,
    "without return cues": RETURN_CUES,
    "without sender behaviour": SENDER_BEHAVIOR,
}
FRICTION_COST_TK = 20.0      # assumed cost of one needless warning (support, abandoned fee)
AVG_LOSS_TK = 4900.0
WARN_EFFECT = 0.45           # share of warned scam value assumed to be prevented


def fit(tr, va, feats):
    dtr = lgb.Dataset(tr[feats], tr["is_scam"])
    dva = lgb.Dataset(va[feats], va["is_scam"], reference=dtr)
    return lgb.train(dict(PARAMS), dtr, num_boost_round=600, valid_sets=[dva],
                     callbacks=[lgb.early_stopping(40, verbose=False)])


def pred(b, df, feats):
    return b.predict(df[feats], num_iteration=b.best_iteration)


def ece(p, y, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[-1] += 1e-9
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows, e = [], 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append({"bin": b + 1, "n": int(m.sum()), "mean_score": round(float(p[m].mean()), 4),
                     "observed_rate": round(float(y[m].mean()), 4)})
        e += m.mean() * abs(p[m].mean() - y[m].mean())
    return round(float(e), 4), rows


def op_point(scores, y, thr):
    flag = scores >= thr
    tp, fp = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum())
    return {"recall": round(tp / max(1, int(y.sum())), 4), "fpr": round(fp / max(1, int((y == 0).sum())), 4),
            "precision": round(tp / max(1, tp + fp), 4)}


def run(data_dir="data", out_dir="reports") -> dict:
    feat = pd.read_csv(Path(data_dir) / "features.csv", parse_dates=["timestamp"])
    feat = feat[feat["scorable"] == 1].reset_index(drop=True)
    tr, va, te = time_split(feat)
    yv, yt = va["is_scam"].to_numpy(), te["is_scam"].to_numpy()
    R: dict = {}

    # 1) ablation
    abl = {}
    for name, drop in ABLATIONS.items():
        feats = [f for f in FEATURES if f not in drop]
        b = fit(tr, va, feats)
        sv, st = pred(b, va, feats), pred(b, te, feats)
        thr = fpr_threshold(sv, yv, FPR_BUDGET["medium"])
        abl[name] = {"features": len(feats), "pr_auc": round(float(average_precision_score(yt, st)), 4),
                     **op_point(st, yt, thr)}
    R["ablation"] = abl

    # 2) calibration (full model)
    base = fit(tr, va, FEATURES)
    sv, st = pred(base, va, FEATURES), pred(base, te, FEATURES)
    e_raw, rows = ece(st, yt)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(sv, yv)
    e_iso, rows_iso = ece(iso.predict(st), yt)
    R["calibration"] = {"ece_raw": e_raw, "ece_isotonic_on_validation": e_iso, "bins_raw": rows,
                        "note": "Scores are used as rankings with false-positive-budget thresholds, so tiers do not "
                                "depend on calibration. Calibrate before showing probabilities to users."}

    # 3) cost-based threshold (chosen on validation, evaluated on test)
    def total_cost(scores, y, thr):
        flag = scores >= thr
        tp, fn = int((flag & (y == 1)).sum()), int(((~flag) & (y == 1)).sum())
        fp = int((flag & (y == 0)).sum())
        return fn * AVG_LOSS_TK + tp * (1 - WARN_EFFECT) * AVG_LOSS_TK + fp * FRICTION_COST_TK

    grid = np.unique(np.quantile(sv, np.linspace(0.90, 0.9995, 120)))
    best = min(grid, key=lambda t: total_cost(sv, yv, t))
    budget_thr = fpr_threshold(sv, yv, FPR_BUDGET["medium"])
    R["cost_threshold"] = {
        "assumptions": {"avg_loss_tk": AVG_LOSS_TK, "warn_effect": WARN_EFFECT, "friction_cost_per_false_warning_tk": FRICTION_COST_TK},
        "fpr_budget_threshold": {"thr": round(float(budget_thr), 4), **op_point(st, yt, budget_thr),
                                 "test_cost_tk": round(total_cost(st, yt, budget_thr))},
        "cost_optimal_threshold": {"thr": round(float(best), 4), **op_point(st, yt, best),
                                   "test_cost_tk": round(total_cost(st, yt, best))},
        "no_warning_cost_tk": round(float(yt.sum() * AVG_LOSS_TK))}

    # 4) logistic regression baseline
    med = tr[FEATURES].median()
    lr = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))
    lr.fit(tr[FEATURES].fillna(med), tr["is_scam"])
    sl, stl = lr.predict_proba(va[FEATURES].fillna(med))[:, 1], lr.predict_proba(te[FEATURES].fillna(med))[:, 1]
    thr_l = fpr_threshold(sl, yv, FPR_BUDGET["medium"])
    R["logistic_baseline"] = {"pr_auc": round(float(average_precision_score(yt, stl)), 4), **op_point(stl, yt, thr_l)}
    R["lightgbm"] = {"pr_auc": abl["full model"]["pr_auc"], **{k: abl["full model"][k] for k in ("recall", "fpr", "precision")}}
    R["test_scams"] = int(yt.sum())

    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(4.5, 4))
    plt.plot([0, max(r["mean_score"] for r in rows) + .05], [0, max(r["mean_score"] for r in rows) + .05], "--", color="gray", label="perfect")
    plt.plot([r["mean_score"] for r in rows], [r["observed_rate"] for r in rows], "o-", label=f"model (ECE {e_raw})")
    plt.xlabel("Mean predicted score"); plt.ylabel("Observed scam rate"); plt.title("Reliability (test)")
    plt.legend(); plt.grid(alpha=.3); plt.tight_layout(); plt.savefig(out / "figures" / "calibration.png", dpi=150); plt.close()
    plt.figure(figsize=(7, 3.6))
    names = list(abl)
    plt.barh(names[::-1], [abl[n]["recall"] * 100 for n in names][::-1])
    plt.xlabel("Recall at warning threshold (%), FPR budget 1.5%"); plt.title("Feature ablation (test, synthetic)")
    plt.tight_layout(); plt.savefig(out / "figures" / "ablation.png", dpi=150); plt.close()
    (out / "evidence.json").write_text(json.dumps(R, indent=2))
    write_md(R, out / "evidence.md")
    return R


def pct(x):
    return f"{x * 100:.1f}%"


def write_md(R, path: Path):
    L = ["# Model Evidence Pack", "",
         f"Synthetic data, chronological split, test set with {R['test_scams']} scams (wide intervals). "
         "Each variant is retrained and its warning threshold is re-chosen on validation (false-positive budget 1.5%).", "",
         "## 1. Feature ablation: does the model depend on one shortcut?", "",
         "| Variant | Features | Recall | False-positive rate | Precision | PR-AUC |", "|---|---|---|---|---|---|"]
    for n, v in R["ablation"].items():
        L.append(f"| {n} | {v['features']} | {pct(v['recall'])} | {pct(v['fpr'])} | {pct(v['precision'])} | {v['pr_auc']} |")
    L += ["", "![Ablation](figures/ablation.png)", "",
          "Reading: a large drop without recipient account age shows reliance on that feature. "
          "The remaining groups show how much the network and return cues add on their own.", "",
          "## 2. Calibration", "",
          f"Expected calibration error on test: **{R['calibration']['ece_raw']}** (raw), "
          f"**{R['calibration']['ece_isotonic_on_validation']}** after isotonic calibration fitted on validation.", "",
          "| Bin | n | Mean score | Observed scam rate |", "|---|---|---|---|"]
    for r in R["calibration"]["bins_raw"]:
        L.append(f"| {r['bin']} | {r['n']} | {r['mean_score']} | {r['observed_rate']} |")
    L += ["", "![Calibration](figures/calibration.png)", "", R["calibration"]["note"], "",
          "## 3. Cost-based threshold vs false-positive budget", "",
          f"Assumptions: average loss {R['cost_threshold']['assumptions']['avg_loss_tk']:.0f} Tk, "
          f"{int(R['cost_threshold']['assumptions']['warn_effect'] * 100)}% of warned scam value prevented, "
          f"{R['cost_threshold']['assumptions']['friction_cost_per_false_warning_tk']:.0f} Tk per needless warning.", "",
          "| Threshold rule | Recall | False-positive rate | Precision | Expected cost on test (Tk) |", "|---|---|---|---|---|"]
    for k, lab in (("fpr_budget_threshold", "False-positive budget (deployed)"), ("cost_optimal_threshold", "Cost-optimal on validation")):
        v = R["cost_threshold"][k]
        L.append(f"| {lab} | {pct(v['recall'])} | {pct(v['fpr'])} | {pct(v['precision'])} | {v['test_cost_tk']:,} |")
    same = R["cost_threshold"]["fpr_budget_threshold"]["thr"] == R["cost_threshold"]["cost_optimal_threshold"]["thr"]
    L += ["", ("The deployed threshold coincides with the cost-optimal one under these assumptions." if same else
               "The cost-optimal threshold differs from the deployed one; compare the two rows."),
          f"Cost with no warnings at all: {R['cost_threshold']['no_warning_cost_tk']:,} Tk.", "",
          "## 4. Simple baseline: logistic regression", "",
          "| Model | Recall | False-positive rate | Precision | PR-AUC |", "|---|---|---|---|---|",
          f"| Logistic regression | {pct(R['logistic_baseline']['recall'])} | {pct(R['logistic_baseline']['fpr'])} | {pct(R['logistic_baseline']['precision'])} | {R['logistic_baseline']['pr_auc']} |",
          f"| LightGBM (deployed) | {pct(R['lightgbm']['recall'])} | {pct(R['lightgbm']['fpr'])} | {pct(R['lightgbm']['precision'])} | {R['lightgbm']['pr_auc']} |", "",
          "## Limits", "",
          "- Synthetic data and a small test set: differences of a few points are not significant.",
          "- Cost assumptions are illustrative and must be replaced with real loss and friction figures.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    R = run(a.data, a.out)
    for n, v in R["ablation"].items():
        print(f"{n:32s} recall={pct(v['recall'])} fpr={pct(v['fpr'])} pr_auc={v['pr_auc']}")
    print("ECE raw/isotonic:", R["calibration"]["ece_raw"], R["calibration"]["ece_isotonic_on_validation"])
    print("cost:", {k: R["cost_threshold"][k]["test_cost_tk"] for k in ("fpr_budget_threshold", "cost_optimal_threshold")}, "no warn:", R["cost_threshold"]["no_warning_cost_tk"])
    print("logistic:", R["logistic_baseline"])


if __name__ == "__main__":
    main()
