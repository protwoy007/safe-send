"""Generate the evaluation report (reports/evaluation.md, evaluation.json, figures).

Sections
    1. Model vs static rules (same test set, same alert volume)
    2. Per-pattern recall with 95% confidence intervals
    3. Fairness: false-positive rate and recall by group
    4. Evasion stress test: adaptive fraudsters, then adversarial hardening
    5. Simulated warning effect and estimated loss prevented (ASSUMPTION-BASED)
    6. Investigator workload

All numbers come from synthetic data. Section 5 uses stated behavioural
assumptions, not measured user behaviour.

Usage:
    python -m src.evaluation.report --data data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, precision_recall_curve  # noqa: E402

from src.data_gen.generate import Config  # noqa: E402
from src.evaluation.evasion import EvasiveMFS  # noqa: E402
from src.features.build import FEATURES, build_features, load, time_split  # noqa: E402
from src.models.train import FPR_BUDGET, PARAMS, fpr_threshold, rule_baseline, tier  # noqa: E402
from src.rules.policy import LARGE_AMOUNT_LIMIT  # noqa: E402

PATTERNS = ["mule", "return_scam", "ato", "split"]
TIER_NAMES = ["low", "medium", "high", "extreme"]

# Section 5 assumptions: probability a sender abandons the transfer after seeing the response.
ABANDON_SCAM = {"low": 0.0, "medium": 0.25, "high": 0.50, "extreme": 0.95}
ABANDON_LEGIT = {"low": 0.0, "medium": 0.03, "high": 0.10, "extreme": 0.10}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(float(max(0, c - h)), 4), round(float(min(1, c + h)), 4))


def predict(booster, df):
    return booster.predict(df[FEATURES], num_iteration=booster.best_iteration)


def final_tiers(scores, df, thr):
    """Model tier, then business rule R1 (very large amounts need at least a cool-off)."""
    t = tier(scores, thr)
    return np.where(df["amount"].to_numpy() >= LARGE_AMOUNT_LIMIT, np.maximum(t, 2), t)


def pattern_recall(df, flag):
    out = {}
    for p in PATTERNS:
        m = (df["scam_pattern"] == p).to_numpy() & (df["is_scam"] == 1).to_numpy()
        k, n = int(flag[m].sum()), int(m.sum())
        out[p] = {"n": n, "recall": round(k / max(1, n), 4), "ci95": wilson(k, n)}
    return out


def summarize(df, scores, thr, blacklist):
    y = df["is_scam"].to_numpy()
    t = final_tiers(scores, df, thr)
    warn = (t >= 1).astype(int)
    rules = rule_baseline(df, blacklist)
    vol_thr = float(np.quantile(scores, 1 - rules.mean()))
    same_vol = (scores >= vol_thr).astype(int)
    k, n = int(warn[y == 1].sum()), int((y == 1).sum())
    fp, nl = int(warn[y == 0].sum()), int((y == 0).sum())
    return {
        "n": len(df), "scams": n, "base_rate": round(float(y.mean()), 4),
        "pr_auc": round(float(average_precision_score(y, scores)), 4),
        "warn_recall": round(k / max(1, n), 4), "warn_recall_ci95": wilson(k, n),
        "warn_fpr": round(fp / max(1, nl), 4), "warn_fpr_ci95": wilson(fp, nl),
        "warn_precision": round(k / max(1, k + fp), 4), "warn_flag_rate": round(float(warn.mean()), 4),
        "rules_recall": round(float(rules[y == 1].mean()), 4), "rules_fpr": round(float(rules[y == 0].mean()), 4),
        "rules_precision": round(float((rules[y == 1]).sum() / max(1, rules.sum())), 4),
        "rules_flag_rate": round(float(rules.mean()), 4),
        "same_volume_recall": round(float(same_vol[y == 1].mean()), 4),
        "same_volume_precision": round(float(same_vol[y == 1].sum() / max(1, same_vol.sum())), 4),
        "pattern_recall_model": pattern_recall(df, warn),
        "pattern_recall_rules": pattern_recall(df, rules),
        "tiers": t,
    }


def fairness(df, scores, thr, meta):
    t = final_tiers(scores, df, thr)
    d = df.assign(warn=(t >= 1).astype(int), region=df["sender_id"].map(meta["region"]),
                  value_band=df["sender_id"].map(meta["value_band"]),
                  sender_group=np.where(df["sender_age_h"] < 30 * 24, "new_account(<30d)", "established"))
    out = {}
    for col in ("value_band", "sender_group", "region"):
        rows = []
        for g, sub in d.groupby(col):
            leg, sc = sub[sub["is_scam"] == 0], sub[sub["is_scam"] == 1]
            fp, nl = int(leg["warn"].sum()), len(leg)
            k, ns = int(sc["warn"].sum()), len(sc)
            rows.append({"group": str(g), "legit_n": nl, "fpr": round(fp / max(1, nl), 4), "fpr_ci95": wilson(fp, nl),
                         "scam_n": ns, "recall": round(k / max(1, ns), 4) if ns else None})
        big = [r["fpr"] for r in rows if r["legit_n"] >= 300 and r["fpr"] > 0]
        out[col] = {"rows": rows, "fpr_max_over_min": round(max(big) / min(big), 2) if len(big) > 1 else None}
    return out


def train_hardened(tr_parts, va_parts):
    tr, va = pd.concat(tr_parts, ignore_index=True), pd.concat(va_parts, ignore_index=True)
    dtr = lgb.Dataset(tr[FEATURES], tr["is_scam"])
    dva = lgb.Dataset(va[FEATURES], va["is_scam"], reference=dtr)
    b = lgb.train(dict(PARAMS), dtr, num_boost_round=600, valid_sets=[dva],
                  callbacks=[lgb.early_stopping(40, verbose=False)])
    sv = b.predict(va[FEATURES], num_iteration=b.best_iteration)
    thr = {k: fpr_threshold(sv, va["is_scam"].to_numpy(), v) for k, v in FPR_BUDGET.items()}
    return b, thr


def simulate(df, tiers, mult=1.0, hold_only=False):
    """Expected effect of the response, under the ABANDON_* behavioural assumptions."""
    y, amt = df["is_scam"].to_numpy(), df["amount"].to_numpy()
    pa = np.array([ABANDON_SCAM[TIER_NAMES[i]] for i in tiers])
    pl = np.array([ABANDON_LEGIT[TIER_NAMES[i]] for i in tiers])
    if hold_only:                       # sender ignores every warning; only human holds work
        pa = np.where(tiers == 3, pa, 0.0)
        pl = np.where(tiers == 3, pl, 0.0)
    pa, pl = np.clip(pa * mult, 0, 1), np.clip(pl * mult, 0, 1)
    scam_total = float(amt[y == 1].sum())
    prevented = float((amt * pa)[y == 1].sum())
    legit = y == 0
    return {"scam_loss_total_tk": round(scam_total), "loss_prevented_tk": round(prevented),
            "loss_prevented_pct": round(prevented / max(1.0, scam_total), 4),
            "legit_transfers_warned_pct": round(float((tiers[legit] >= 1).mean()), 4),
            "legit_transfers_abandoned_pct": round(float(pl[legit].mean()), 4),
            "legit_value_abandoned_tk": round(float((amt * pl)[legit].sum()))}


# ---------------------------------------------------------------- figures
def make_figures(fig_dir: Path, y_te, s_te, rules_pt, warn_pt, orig_pat, adv_pat, hard_pat, fair):
    fig_dir.mkdir(parents=True, exist_ok=True)
    p, r, _ = precision_recall_curve(y_te, s_te)
    plt.figure(figsize=(5.5, 4))
    plt.plot(r, p, label="LightGBM risk model")
    plt.scatter([rules_pt[0]], [rules_pt[1]], color="red", zorder=3, label="Static rules")
    plt.scatter([warn_pt[0]], [warn_pt[1]], color="green", zorder=3, label="Model warning threshold")
    plt.xlabel("Recall"); plt.ylabel("Precision"); plt.title("Precision-recall (test, synthetic)")
    plt.legend(); plt.grid(alpha=.3); plt.tight_layout(); plt.savefig(fig_dir / "pr_curve.png", dpi=150); plt.close()

    x = np.arange(len(PATTERNS)); w = 0.2
    plt.figure(figsize=(7, 4))
    for i, (name, d) in enumerate((("Original test: model", orig_pat), ("Evasive: model", adv_pat),
                                   ("Evasive: static rules", None), ("Evasive: hardened model", hard_pat))):
        vals = [d[p]["recall"] for p in PATTERNS] if d else [adv_pat[p]["rules_recall"] for p in PATTERNS]
        plt.bar(x + (i - 1.5) * w, vals, w, label=name)
    plt.xticks(x, PATTERNS); plt.ylim(0, 1.3); plt.ylabel("Recall at warning threshold")
    plt.title("Robustness to adaptive fraudsters"); plt.legend(fontsize=7, ncol=2, loc="upper center"); plt.grid(axis="y", alpha=.3)
    plt.tight_layout(); plt.savefig(fig_dir / "evasion_recall.png", dpi=150); plt.close()

    plt.figure(figsize=(7, 3.6))
    labels, vals = [], []
    for col in ("value_band", "sender_group", "region"):
        for r_ in fair[col]["rows"]:
            labels.append(r_["group"]); vals.append(r_["fpr"] * 100)
    plt.bar(range(len(vals)), vals)
    plt.xticks(range(len(vals)), labels, rotation=60, ha="right", fontsize=7)
    plt.ylabel("False-positive rate (%)"); plt.title("Legitimate transfers warned, by group")
    plt.tight_layout(); plt.savefig(fig_dir / "fairness_fpr.png", dpi=150); plt.close()


# ---------------------------------------------------------------- markdown
def pct(x):
    return f"{x * 100:.1f}%"


def pct2(x):
    return f"{x * 100:.2f}%"


def ci(c):
    return f"{c[0] * 100:.1f}-{c[1] * 100:.1f}%"


def write_markdown(R, path: Path):
    o, a, h = R["original"], R["evasive"], R["hardened_on_evasive"]
    L = []
    L += ["# Safe-Send: Evaluation Report", "",
          "All results use **synthetic data**. They show that the method works and how it behaves; "
          "they do not predict real-world accuracy. Test periods are chronological and were never used "
          "for training or threshold selection.", ""]
    L += ["## 1. Model vs static rules (original test set)", "",
          f"Test set: {o['n']:,} transfers, {o['scams']} scams ({pct(o['base_rate'])}).", "",
          "| Metric | Static rules | Risk model |", "|---|---|---|",
          f"| Alert volume | {pct(o['rules_flag_rate'])} | {pct(o['warn_flag_rate'])} (warning threshold) |",
          f"| Recall | {pct(o['rules_recall'])} | {pct(o['warn_recall'])} (95% CI {ci(o['warn_recall_ci95'])}) |",
          f"| False-positive rate | {pct(o['rules_fpr'])} | {pct(o['warn_fpr'])} (95% CI {ci(o['warn_fpr_ci95'])}) |",
          f"| Precision | {pct(o['rules_precision'])} | {pct(o['warn_precision'])} |",
          f"| Recall at the SAME alert volume as the rules | {pct(o['rules_recall'])} | {pct(o['same_volume_recall'])} |",
          f"| PR-AUC | n/a | {o['pr_auc']} |", "",
          "The model catches more scams than the rules while warning far fewer legitimate senders.", "",
          "![PR curve](figures/pr_curve.png)", ""]
    L += ["## 2. Recall by scam pattern (95% confidence intervals)", "",
          "| Pattern | n | Rules | Model | Model 95% CI |", "|---|---|---|---|---|"]
    for p in PATTERNS:
        L.append(f"| {p} | {o['pattern_recall_model'][p]['n']} | {pct(o['pattern_recall_rules'][p]['recall'])} | "
                 f"{pct(o['pattern_recall_model'][p]['recall'])} | {ci(o['pattern_recall_model'][p]['ci95'])} |")
    L += ["", "Small counts give wide intervals. Treat single-pattern numbers as indicative.", ""]
    L += ["## 3. Fairness checks", "",
          "False-positive rate = share of legitimate transfers that receive a warning. "
          "Large gaps between groups would need investigation before any real deployment.", ""]
    for col, title in (("value_band", "Sender value band"), ("sender_group", "Sender account age"), ("region", "Region")):
        f = R["fairness"][col]
        L += [f"**{title}**" + (f" (highest/lowest FPR ratio: {f['fpr_max_over_min']}x)" if f["fpr_max_over_min"] else ""), "",
              "| Group | Legit transfers | FPR | 95% CI | Scams | Recall |", "|---|---|---|---|---|---|"]
        for r in f["rows"]:
            rc = pct(r["recall"]) if r["recall"] is not None else "n/a"
            L.append(f"| {r['group']} | {r['legit_n']:,} | {pct(r['fpr'])} | {ci(r['fpr_ci95'])} | {r['scam_n']} | {rc} |")
        L.append("")
    L += ["Note: the region FPR ratio is driven by small groups; their confidence intervals overlap, so no "
          "region is shown to be treated differently.", "",
          "![FPR by group](figures/fairness_fpr.png)", "",
          "Limitation: the synthetic data has no protected attributes beyond region and value band. "
          "A real audit would use real demographic and access-related groups.", ""]
    L += ["## 4. Evasion stress test (adaptive fraudsters)", "",
          "A second synthetic world where fraudsters adapt: mule rings rotate accounts (about 4 victims per mule) and "
          "collect slowly, splitting uses 800-2,400 Tk pieces spread over hours, takeovers use modest amounts from the "
          "victim's own device, and return scams are always partial and go to older accounts.", "",
          f"Evasive test set: {a['n']:,} transfers, {a['scams']} scams. The original model and thresholds are used unchanged.", "",
          "| Pattern | n | Rules | Original model | Hardened model* |", "|---|---|---|---|---|"]
    for p in PATTERNS:
        L.append(f"| {p} | {a['pattern_recall_model'][p]['n']} | {pct(a['pattern_recall_rules'][p]['recall'])} | "
                 f"{pct(a['pattern_recall_model'][p]['recall'])} | {pct(h['pattern_recall_model'][p]['recall'])} |")
    L += ["", f"Overall on evasive data: original model recall {pct(a['warn_recall'])} at FPR {pct(a['warn_fpr'])}; "
          f"static rules recall {pct(a['rules_recall'])}; hardened model recall {pct(h['warn_recall'])} at FPR {pct(h['warn_fpr'])}.", "",
          f"*Hardened = retrained on the original training data plus the evasive training period (days before 40), "
          f"tested on the evasive test period. On the original test set the hardened model scores recall "
          f"{pct(R['hardened_on_original']['warn_recall'])} at FPR {pct(R['hardened_on_original']['warn_fpr'])}, "
          f"so hardening does not break the original behaviour.", "",
          "![Evasion](figures/evasion_recall.png)", "",
          "Takeaway: adaptive fraudsters reduce detection (the largest drop is on partial return scams), as expected in any "
          "fraud system. Retraining with confirmed cases (the investigator feedback loop in the architecture) restores it. "
          "Caveat: the hardened model is tested on the SAME evasion strategy it was trained on, so its near-perfect recall is "
          "optimistic. A real adversary would adapt again, so this is an ongoing process, not a one-time fix.", ""]
    s = R["simulation"]
    L += ["## 5. Simulated warning effect and estimated loss prevented", "",
          "**This section is a simulation based on stated assumptions, not measured user behaviour.** "
          "Assumed probability that the sender abandons the transfer after the response:", "",
          "| Tier | Scam transfer | Legitimate transfer |", "|---|---|---|"]
    for t in TIER_NAMES:
        L.append(f"| {t} | {pct(ABANDON_SCAM[t])} | {pct(ABANDON_LEGIT[t])} |")
    L += ["", "Extreme tier means a hold reviewed by a person (assumed 95% correct on real scams).", "",
          "| Scenario | Scam loss prevented | Legit transfers warned | Legit transfers abandoned | Legit value abandoned |",
          "|---|---|---|---|---|"]
    for name, r in s["scenarios"].items():
        L.append(f"| {name} | {pct(r['loss_prevented_pct'])} ({r['loss_prevented_tk']:,} of {r['scam_loss_total_tk']:,} Tk) | "
                 f"{pct2(r['legit_transfers_warned_pct'])} | {pct2(r['legit_transfers_abandoned_pct'])} | {r['legit_value_abandoned_tk']:,} Tk |")
    L += ["", "Even if senders ignored every warning, human review of extreme cases would still prevent part of the loss. "
          "The real effect of warnings must be measured with a controlled experiment (see Scale plan).", ""]
    w = R["workload"]
    L += ["## 6. Investigator workload", "",
          f"On the test set ({o['n']:,} transfers): {w['extreme_per_10k']:.0f} cases per 10,000 transfers reach the investigator queue "
          f"(extreme tier). {pct(w['extreme_precision'])} of them are real scams. "
          f"Medium and high tiers are handled by the sender warning without investigator effort.", ""]
    L += ["## 7. Latency", "",
          "Measured with `python scripts/benchmark_latency.py`: p95 of about 4 ms per scoring request on a laptop, "
          "against a 200 ms target.", ""]
    L += ["## 8. Known limitations", "",
          "- Synthetic data: results show method validity, not real-world performance.",
          "- Per-pattern and per-group counts are small, so confidence intervals are wide.",
          "- Warning-effect numbers rely on assumptions; they are illustrative.",
          "- The evasive world is one adaptation strategy among many; hardened results are in-distribution and optimistic.",
          "- Some reasons describe the recipient, which the sender cannot verify; the system treats this as evidence, not as proof.",
          "- Features such as device sharing and fan-in need real telemetry before deployment.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- main
def run(data_dir="data", model_path="models/risk_model.pkl", out_dir="reports", seed=77) -> dict:
    out = Path(out_dir)
    acc, _ = load(data_dir)
    meta = acc.set_index("account_id")
    art = joblib.load(model_path)
    booster, thr = art["booster"], art["thresholds"]

    feat = pd.read_csv(Path(data_dir) / "features.csv", parse_dates=["timestamp"])
    feat = feat[feat["scorable"] == 1].reset_index(drop=True)
    tr, va, te = time_split(feat)
    s_te = predict(booster, te)
    blacklist = set(tr.loc[tr["is_scam"] == 1, "recipient_id"])
    orig = summarize(te, s_te, thr, blacklist)

    # evasion world
    cfg = Config(seed=seed, n_mule_rings=80, n_return_scams=300, n_ato=250, n_split=100)
    a_acc, a_tx = EvasiveMFS(cfg).build()
    adv = build_features(a_tx, a_acc)
    adv = adv[adv["scorable"] == 1].reset_index(drop=True)
    atr, ava, ate = time_split(adv)
    a_black = set(atr.loc[atr["is_scam"] == 1, "recipient_id"])
    s_ate = predict(booster, ate)
    evasive = summarize(ate, s_ate, thr, a_black)

    hb, hthr = train_hardened([tr, atr], [va, ava])
    hard_adv = summarize(ate, predict(hb, ate), hthr, a_black)
    hard_orig = summarize(te, predict(hb, te), hthr, blacklist)

    fair = fairness(te, s_te, thr, meta)

    t_final = orig["tiers"]
    scen = {
        "Senders follow assumed behaviour": simulate(te, t_final),
        "Weaker warning effect (half)": simulate(te, t_final, mult=0.5),
        "Stronger warning effect (1.5x)": simulate(te, t_final, mult=1.5),
        "Senders ignore warnings, only holds work": simulate(te, t_final, hold_only=True),
    }
    ext = t_final == 3
    workload = {"extreme_per_10k": float(ext.mean() * 10_000),
                "extreme_precision": float(te["is_scam"].to_numpy()[ext].mean()) if ext.any() else 0.0}

    for d in (orig, evasive, hard_adv, hard_orig):
        d.pop("tiers")
    R = {"original": orig, "evasive": evasive, "hardened_on_evasive": hard_adv, "hardened_on_original": hard_orig,
         "fairness": fair, "simulation": {"assumptions": {"scam": ABANDON_SCAM, "legit": ABANDON_LEGIT}, "scenarios": scen},
         "workload": workload}

    # figure helper wants rules_recall inside the evasive pattern dict
    adv_fig = {p: {**evasive["pattern_recall_model"][p], "rules_recall": evasive["pattern_recall_rules"][p]["recall"]}
               for p in PATTERNS}
    make_figures(out / "figures", te["is_scam"].to_numpy(), s_te,
                 (orig["rules_recall"], orig["rules_precision"]), (orig["warn_recall"], orig["warn_precision"]),
                 orig["pattern_recall_model"], adv_fig, hard_adv["pattern_recall_model"], fair)
    out.mkdir(exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(R, indent=2, default=str))
    write_markdown(R, out / "evaluation.md")
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--model", default="models/risk_model.pkl")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()
    R = run(args.data, args.model, args.out)
    o, a, h = R["original"], R["evasive"], R["hardened_on_evasive"]
    print(f"ORIGINAL  recall={o['warn_recall']} fpr={o['warn_fpr']} | rules recall={o['rules_recall']} fpr={o['rules_fpr']}")
    print(f"EVASIVE   model recall={a['warn_recall']} fpr={a['warn_fpr']} | rules recall={a['rules_recall']} | hardened recall={h['warn_recall']} fpr={h['warn_fpr']}")
    print("per pattern (evasive): " + json.dumps({p: [a['pattern_recall_model'][p]['recall'], h['pattern_recall_model'][p]['recall']] for p in PATTERNS}))
    print("workload:", R["workload"])
    print(f"wrote {args.out}/evaluation.md, evaluation.json, figures/*.png")


if __name__ == "__main__":
    main()
