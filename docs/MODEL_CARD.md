# Model card: Safe-Send recipient risk model

## Purpose
Scores a mobile-wallet transfer before the sender confirms it. The score selects one of four tiers: allow, warn, warn with 30-second cool-off, or hold for human review. Nothing is blocked automatically.

## Model
- LightGBM binary classifier, 32 features computed from past data only (tabular, network and scam-cue features).
- Training: chronological split (train before day 40, validation days 40-49, test day 50 onward), early stopping on validation, `scale_pos_weight=5`.
- Tier thresholds are set on validation by false-positive budget (medium 1.5%, high 0.4%, extreme 0.1% of legitimate transfers), never on test.
- The raw score is a ranking score, not a probability. Tiers do not need calibrated probabilities.
- Explanations: SHAP attributions grouped into 9 reason groups, rendered from fixed English and Bangla templates. No generated free text reaches the sender.

## Intended use
Pre-confirmation warnings and an investigator review queue in a mobile financial service. Human decision for every hold.

## Out of scope
Automatic blocking, freezing or account closure. Credit or identity decisions. Use on real customers without validation on real data.

## Data
Synthetic only (see `DATA_SHEET.md`): 75,682 transfers, 3,296 accounts, 60 days, 1.2% scam transfers, four scam patterns plus legitimate look-alikes.

## Results (synthetic test set, 14,018 transfers, 100 scams)
- Warning threshold: recall 95.0%, precision 50.8%, false-positive rate 0.66%. PR-AUC 0.788, ROC-AUC 0.998.
- Static rules at the same alert volume: recall 57%, precision 10.3%.
- Ablation (`reports/evidence.md`): without network features recall 82.0%; without sender behaviour 84.0%; without return cues 90.0%; without recipient account age 95.0% (no change).
- Logistic regression baseline: recall 90.0% at the same false-positive budget. A simple model is strong on this synthetic data.
- Calibration error (raw score): 0.002.
- Evasion stress test: recall falls to 88.7% against adapted fraud; retraining on the adapted cases recovers it, which is optimistic.

## Fairness
False-positive rate on legitimate transfers: 0.2% to 0.9% across regions, 0.6% to 0.8% across value bands, 0% for new accounts, 0.7% for established accounts. Intervals overlap. The synthetic data has no other attributes, so a real audit is still needed.

## Limitations
- Synthetic data: results show the method works, not real-world accuracy.
- Only 100 scam transfers in the test set; per-pattern numbers are noisy.
- Some reasons describe the recipient (for example earlier cash-outs), which the sender cannot verify.
- Bangla wording needs review by a native speaker.
- Fraudsters adapt; the model needs monitoring and periodic retraining.

## Human oversight and security
Extreme cases go to an investigator who releases or rejects; every decision is written to an append-only audit log. Business rules (R1 to R4) can only raise a tier. Investigator endpoints need an API key; rate limiting and security headers are enabled.
