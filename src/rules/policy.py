"""Business rules, kept SEPARATE from the ML model.

The model only supplies a risk score and tier. This module turns the tier into an
action and applies hard rules. Rules can only RAISE the tier, never lower it.
Nothing here auto-blocks a transfer: the most severe outcome is a hold that a
human investigator must resolve.
"""
from __future__ import annotations

TIER_ORDER = ["low", "medium", "high", "extreme"]
COOLOFF_SECONDS = 30
LARGE_AMOUNT_LIMIT = 40_000      # hard rule R1: very large transfers need at least a cool-off
REPORTS_FOR_FLAG = 3             # hard rule R2: recipient reported by this many senders

ACTIONS = {
    "low": "allow",
    "medium": "warn",
    "high": "warn_cooloff",       # warning + 30s cool-off + report option
    "extreme": "hold_for_review",  # human investigator decides
}


def _raise_to(tier: str, minimum: str) -> str:
    return max(tier, minimum, key=TIER_ORDER.index)


def apply_policy(model_tier: str, amount: float, recipient_reports: int, recipient_confirmed_fraud: bool) -> dict:
    tier, triggered = model_tier, []
    if amount >= LARGE_AMOUNT_LIMIT:
        tier = _raise_to(tier, "high")
        triggered.append("R1_LARGE_AMOUNT")
    if recipient_confirmed_fraud:
        tier = _raise_to(tier, "extreme")
        triggered.append("R3_INVESTIGATOR_CONFIRMED_FRAUD")
    elif recipient_reports >= REPORTS_FOR_FLAG:
        tier = _raise_to(tier, "high")
        triggered.append("R2_REPEATED_USER_REPORTS")
    return {
        "model_tier": model_tier,
        "final_tier": tier,
        "action": ACTIONS[tier],
        "cooloff_seconds": COOLOFF_SECONDS if ACTIONS[tier] == "warn_cooloff" else 0,
        "triggered_rules": triggered,
        "can_report": tier in ("medium", "high", "extreme"),
    }
