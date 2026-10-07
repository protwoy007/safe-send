"""Impact calculator: expected net benefit of Safe-Send under explicit assumptions.

Every input is an assumption the reader can change. Nothing here is a measured result
on real transfers; the pilot design shows how the real effect would be measured.
"""
from __future__ import annotations

from statistics import NormalDist

DEFAULTS = dict(
    monthly_transfers=1_000_000,   # transfers per month at the pilot scale
    scam_rate=0.007,               # share of transfers that are scams (synthetic test set: 0.71%)
    avg_loss_tk=2_800.0,           # average amount lost per scam transfer (Tk; synthetic average)
    recall=0.95,                   # share of scams that receive a warning or hold (test: 95%)
    warn_effect=0.5,               # share of warned scam senders who stop (ASSUMPTION)
    false_positive_rate=0.0066,    # share of legitimate transfers warned (test: 0.66%)
    legit_abandon=0.05,            # share of warned legitimate senders who abandon (ASSUMPTION)
    avg_legit_value_tk=1_350.0,    # average legitimate transfer value (Tk; synthetic average)
    fee_rate=0.01,                 # revenue per transfer as a share of its value
    cases_per_10k=13.0,            # investigator cases per 10,000 transfers (test: 13)
    cost_per_case_tk=200.0,        # investigator cost per case (Tk)
    pilot_relative_reduction=0.30,  # relative drop in scam rate the pilot should detect
)

DISCLAIMER = ("Assumption-based estimate. Recall and false-positive rate come from a synthetic test set; "
              "warning effect, abandon rate and costs are assumptions. Real values must be measured in a pilot.")


def pilot_sample_size(p: float, reduction: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Transfers per arm to detect a relative drop in the scam rate (two-sided two-proportion test)."""
    p1, p2 = p, p * (1 - reduction)
    if p1 <= 0 or p1 == p2:
        return 0
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return int(round(z * z * (p1 * (1 - p1) + p2 * (1 - p2)) / (p1 - p2) ** 2))


def _net(i: dict, warn_effect: float) -> tuple[dict, float]:
    scams = i["monthly_transfers"] * i["scam_rate"]
    warned = scams * i["recall"]
    prevented = warned * warn_effect * i["avg_loss_tk"]
    legit_warned = i["monthly_transfers"] * (1 - i["scam_rate"]) * i["false_positive_rate"]
    revenue_lost = legit_warned * i["legit_abandon"] * i["avg_legit_value_tk"] * i["fee_rate"]
    cost = i["monthly_transfers"] / 10_000 * i["cases_per_10k"] * i["cost_per_case_tk"]
    res = dict(scams_per_month=round(scams), scams_warned=round(warned), prevented_value_tk=round(prevented),
               legit_warned=round(legit_warned), revenue_lost_tk=round(revenue_lost),
               investigator_cost_tk=round(cost), net_benefit_tk=round(prevented - revenue_lost - cost))
    return res, warned * i["avg_loss_tk"]


def compute(**overrides) -> dict:
    i = {**DEFAULTS, **{k: v for k, v in overrides.items() if v is not None}}
    results, loss_at_full = _net(i, i["warn_effect"])
    burden = results["revenue_lost_tk"] + results["investigator_cost_tk"]
    results["break_even_warn_effect"] = round(min(1.0, burden / loss_at_full), 4) if loss_at_full > 0 else None
    sens = [{"warn_effect": w, "net_benefit_tk": _net(i, w)[0]["net_benefit_tk"]}
            for w in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    n = pilot_sample_size(i["scam_rate"], i["pilot_relative_reduction"])
    pilot = {"n_per_arm": n,
             "assumption": (f"A/B test, 5% significance, 80% power, to detect a {i['pilot_relative_reduction']:.0%} "
                            f"relative drop in the scam rate from {i['scam_rate']:.2%}. Control: no warning. "
                            "Treatment: Safe-Send tiers. Success metrics: scam loss per transfer, false-warning rate, "
                            "abandon rate of legitimate transfers, investigator minutes per case.")}
    return {"inputs": i, "results": results, "sensitivity": sens, "pilot": pilot, "disclaimer": DISCLAIMER}
