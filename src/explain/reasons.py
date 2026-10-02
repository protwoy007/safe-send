"""Explainable risk output for Safe-Send: SHAP attribution + fixed plain-language templates.

How an explanation is produced
    1. LightGBM gives the risk score; thresholds map it to a tier (low/medium/high/extreme).
    2. SHAP (TreeExplainer) attributes the score to features.
    3. Features are grouped into human-meaningful reason groups (e.g. all "fan-in"
       features -> one reason). Only groups that PUSH RISK UP are shown.
    4. Each group is rendered from a FIXED template using the real feature values.
       Text is never free-form LLM output; a reason is shown only if its condition holds
       (so the message always matches the data).

The response keeps prediction, evidence and generated text separate (Transparency).

Demo:
    python -m src.explain.reasons --data data --n 4 --lang en
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from src.features.build import FEATURES

warnings.filterwarnings("ignore", message="LightGBM binary classifier with TreeExplainer")

TIERS = ["low", "medium", "high", "extreme"]
MIN_IMPACT = 0.10  # minimum SHAP (log-odds) for a reason to be shown

GROUPS = {
    "FAN_IN": ["recipient_senders_1h", "recipient_senders_24h", "recipient_senders_all",
               "recipient_in_count_1h", "recipient_in_out_ratio"],
    "NEW_ACCOUNT": ["recipient_age_h"],
    "RETURN": ["sender_received_3h", "returning_recent_received", "return_to_original_sender"],
    "AMOUNT": ["amount", "log_amount", "amount_to_mean_ratio", "sender_mean_amount_prior"],
    "DEVICE": ["is_new_device", "device_shared_senders"],
    "NEW_RECIPIENT": ["is_new_recipient", "pair_count_prior"],
    "TIME": ["hour", "is_night", "day_of_week", "is_month_end"],
    "VELOCITY": ["sender_tx_15m", "sender_amount_15m", "sender_tx_1h"],
    "CASHOUT": ["recipient_cashout_prior", "recipient_out_count_prior"],
}
FEATURE_TO_GROUP = {f: g for g, fs in GROUPS.items() for f in fs}

ACTIONS = {
    "en": {
        "low": "No risk signals found.",
        "medium": "Check before you send. Make sure you know and trust this recipient.",
        "high": "High risk. Please wait 30 seconds before confirming. You can report this recipient.",
        "extreme": "This transfer is paused for review by the fraud team. Nothing was blocked "
                   "automatically; a person will decide.",
    },
    "bn": {
        "low": "কোনো ঝুঁকির লক্ষণ পাওয়া যায়নি।",
        "medium": "পাঠানোর আগে একবার যাচাই করুন। প্রাপককে আপনি চেনেন ও বিশ্বাস করেন কিনা নিশ্চিত হোন।",
        "high": "উচ্চ ঝুঁকি। নিশ্চিত করার আগে ৩০ সেকেন্ড অপেক্ষা করুন। চাইলে এই প্রাপককে রিপোর্ট করতে পারেন।",
        "extreme": "এই লেনদেনটি জালিয়াতি প্রতিরোধ দলের পর্যালোচনার জন্য থামানো হয়েছে। "
                   "কিছুই স্বয়ংক্রিয়ভাবে বাতিল করা হয়নি; একজন মানুষ সিদ্ধান্ত নেবেন।",
    },
}
_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def _n(v, lang: str) -> str:
    s = str(int(round(float(v))))
    return s.translate(_BN_DIGITS) if lang == "bn" else s


def _age(hours: float, lang: str) -> str:
    if hours < 1:
        return "less than an hour" if lang == "en" else "এক ঘণ্টারও কম সময়"
    if hours < 48:
        return f"{_n(hours, lang)} hours" if lang == "en" else f"{_n(hours, lang)} ঘণ্টা"
    d = hours / 24
    return f"{_n(d, lang)} days" if lang == "en" else f"{_n(d, lang)} দিন"


# --------------------------------------------------------------- reason templates
# Each renderer returns (text, evidence) or None when the condition does not hold.
def _fan_in(r, lang):
    for col, en, bn, min_n in (("recipient_senders_1h", "in the last hour", "গত ১ ঘণ্টায়", 3),
                               ("recipient_senders_24h", "in the last 24 hours", "গত ২৪ ঘণ্টায়", 3),
                               ("recipient_senders_all", "so far", "এ পর্যন্ত", 5)):
        if r[col] >= min_n:
            n = _n(r[col], lang)
            text = (f"This account received money from {n} different people {en}." if lang == "en"
                    else f"এই অ্যাকাউন্টটি {bn} {n} জন আলাদা মানুষের কাছ থেকে টাকা পেয়েছে।")
            return text, {col: float(r[col])}
    return None


def _new_account(r, lang):
    if r["recipient_age_h"] > 14 * 24:
        return None
    a = _age(r["recipient_age_h"], lang)
    text = (f"The recipient account is only {a} old." if lang == "en"
            else f"প্রাপকের অ্যাকাউন্টটি মাত্র {a} আগে খোলা হয়েছে।")
    return text, {"recipient_age_h": round(float(r["recipient_age_h"]), 1)}


def _return(r, lang):
    if r["returning_recent_received"] == 1 and r["return_to_original_sender"] == 0:
        text = ("You are sending back money you just received, but to a different account than it came from."
                if lang == "en" else
                "আপনি এইমাত্র পাওয়া টাকা ফেরত পাঠাচ্ছেন, কিন্তু যে অ্যাকাউন্ট থেকে এসেছে সেটিতে নয়, অন্য একটি অ্যাকাউন্টে।")
        return text, {"returning_recent_received": 1, "return_to_original_sender": 0}
    return None


def _amount(r, lang):
    ratio = r["amount_to_mean_ratio"]
    if pd.isna(ratio) or ratio < 2.0:
        return None
    x = f"{ratio:.1f}"
    text = (f"This amount is {x}x your usual transfer." if lang == "en"
            else f"এই পরিমাণ আপনার স্বাভাবিক লেনদেনের {x.translate(_BN_DIGITS)} গুণ।")
    return text, {"amount_to_mean_ratio": round(float(ratio), 2), "amount": float(r["amount"])}


def _device(r, lang):
    if r["is_new_device"] == 1:
        text = ("This transfer is from a device not used on your account before." if lang == "en"
                else "এই লেনদেন এমন একটি ডিভাইস থেকে হচ্ছে যা আগে আপনার অ্যাকাউন্টে ব্যবহার হয়নি।")
        return text, {"is_new_device": 1}
    if r["device_shared_senders"] >= 1:
        n = _n(r["device_shared_senders"], lang)
        text = (f"This device has been used on {n} other accounts." if lang == "en"
                else f"এই ডিভাইসটি আরও {n}টি অ্যাকাউন্টে ব্যবহার হয়েছে।")
        return text, {"device_shared_senders": float(r["device_shared_senders"])}
    return None


def _new_recipient(r, lang):
    if r["is_new_recipient"] != 1:
        return None
    text = ("You have never sent money to this recipient before." if lang == "en"
            else "আপনি এই প্রাপককে আগে কখনো টাকা পাঠাননি।")
    return text, {"is_new_recipient": 1}


def _time(r, lang):
    if r["is_night"] != 1:
        return None
    h = _n(r["hour"], lang)
    text = (f"This transfer is at an unusual hour ({h}:00)." if lang == "en"
            else f"লেনদেনটি অস্বাভাবিক সময়ে ({h}টা) হচ্ছে।")
    return text, {"hour": int(r["hour"])}


def _velocity(r, lang):
    if r["sender_tx_15m"] < 2:
        return None
    n = _n(r["sender_tx_15m"], lang)
    text = (f"You have already made {n} transfers in the last 15 minutes." if lang == "en"
            else f"গত ১৫ মিনিটে আপনি ইতিমধ্যে {n}টি লেনদেন করেছেন।")
    return text, {"sender_tx_15m": float(r["sender_tx_15m"])}


def _cashout(r, lang):
    if r["recipient_cashout_prior"] < 1:
        return None
    text = ("This account has quickly cashed out money it received before." if lang == "en"
            else "এই অ্যাকাউন্ট আগে টাকা পাওয়ার পর দ্রুত তা তুলে নিয়েছে।")
    return text, {"recipient_cashout_prior": float(r["recipient_cashout_prior"])}


RENDERERS = {"FAN_IN": _fan_in, "NEW_ACCOUNT": _new_account, "RETURN": _return, "AMOUNT": _amount,
             "DEVICE": _device, "NEW_RECIPIENT": _new_recipient, "TIME": _time,
             "VELOCITY": _velocity, "CASHOUT": _cashout}


# --------------------------------------------------------------- explainer
class Explainer:
    def __init__(self, booster, thresholds: dict, features: list[str] = FEATURES):
        self.booster = booster
        self.thr = thresholds
        self.features = features
        self.shap = shap.TreeExplainer(booster)

    @classmethod
    def from_pickle(cls, path: str | Path = "models/risk_model.pkl") -> "Explainer":
        art = joblib.load(path)
        return cls(art["booster"], art["thresholds"], art["features"])

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(X[self.features])

    def tier_of(self, score: float) -> str:
        t = self.thr
        if score >= t["extreme"]:
            return "extreme"
        if score >= t["high"]:
            return "high"
        if score >= t["medium"]:
            return "medium"
        return "low"

    def _shap_values(self, X: pd.DataFrame) -> np.ndarray:
        sv = self.shap.shap_values(X[self.features])
        if isinstance(sv, list):
            sv = sv[-1]
        sv = np.asarray(sv)
        return sv[:, :, -1] if sv.ndim == 3 else sv

    def explain(self, X: pd.DataFrame, lang: str = "en", top_n: int = 3) -> list[dict]:
        """Explain one or more transactions (rows of the feature frame)."""
        scores = self.score(X)
        sv = self._shap_values(X)
        out = []
        for i in range(len(X)):
            row = X.iloc[i]
            tier = self.tier_of(float(scores[i]))
            impact = {}
            for j, f in enumerate(self.features):
                g = FEATURE_TO_GROUP.get(f)
                if g:
                    impact[g] = impact.get(g, 0.0) + float(sv[i, j])
            reasons = []
            if tier != "low":
                for g, imp in sorted(impact.items(), key=lambda kv: -kv[1]):
                    if imp < MIN_IMPACT or len(reasons) >= top_n:
                        continue
                    rendered = RENDERERS[g](row, lang)
                    if rendered:
                        text, ev = rendered
                        reasons.append({"code": g, "text": text, "impact": round(imp, 3), "evidence": ev})
            out.append({
                "risk_score": round(float(scores[i]), 4),
                "tier": tier,
                "action_message": ACTIONS[lang][tier],
                "reasons": reasons,
                "explanation_source": "SHAP attribution + fixed templates (no free-form generation)",
            })
        return out


def main():
    p = argparse.ArgumentParser(description="Show example explanations")
    p.add_argument("--data", default="data")
    p.add_argument("--model", default="models/risk_model.pkl")
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--lang", default="en", choices=["en", "bn"])
    args = p.parse_args()

    ex = Explainer.from_pickle(args.model)
    feat = pd.read_csv(Path(args.data) / "features.csv", parse_dates=["timestamp"])
    feat = feat[(feat["scorable"] == 1)]
    day = (feat["timestamp"] - feat["timestamp"].min().normalize()).dt.days
    test = feat[day >= 50].reset_index(drop=True)
    test["score"] = ex.score(test)
    for pattern in ("return_scam", "mule", "ato", "split"):
        sub = test[(test["scam_pattern"] == pattern) & (test["is_scam"] == 1)]
        if len(sub) == 0:
            continue
        best = sub.sort_values("score", ascending=False).head(max(1, args.n // 4))
        for _, r in best.iterrows():
            e = ex.explain(pd.DataFrame([r]), lang=args.lang)[0]
            print(f"\n=== {pattern}  score={e['risk_score']}  tier={e['tier']}")
            print(e["action_message"])
            for rs in e["reasons"]:
                print(f"  - [{rs['code']}] {rs['text']}  (impact {rs['impact']})")
    legit = test[(test["is_scam"] == 0) & (test["score"] >= ex.thr["medium"])].head(2)
    for _, r in legit.iterrows():
        e = ex.explain(pd.DataFrame([r]), lang=args.lang)[0]
        print(f"\n=== LEGIT transfer wrongly warned ({r['scam_pattern']})  tier={e['tier']}")
        for rs in e["reasons"]:
            print(f"  - [{rs['code']}] {rs['text']}")


if __name__ == "__main__":
    main()
