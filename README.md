# Safe-Send: Recipient Risk Check

**AI Hackathon 2026 | DIU CPC × upay | Track 01: Trust & Risk Intelligence**

Safe-Send checks a mobile-wallet transfer **before it is confirmed**. It scores the recipient and the transaction in real time, warns the sender in plain language (English and Bangla), and sends the riskiest cases to a human investigator. **Nothing is ever auto-blocked.** A person decides on every hold.

**Demo video:** `https://youtu.be/alHAcqFK2Sw`

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Features and how AI is used](#2-features-and-how-ai-is-used)
3. [Results](#3-results)
4. [Technology stack](#4-technology-stack)
5. [Requirements](#5-requirements)
6. [Installation and setup](#6-installation-and-setup)
7. [Environment variables](#7-environment-variables)
8. [Run and build commands](#8-run-and-build-commands)
9. [Live deployment](#9-live-deployment)
10. [Testing instructions](#10-testing-instructions)
11. [API reference](#11-api-reference)
12. [Architecture](#12-architecture)
13. [Synthetic data](#13-synthetic-data)
14. [Responsible AI and security](#14-responsible-ai-and-security)
15. [Other configuration](#15-other-configuration)
16. [Limitations and path to production](#16-limitations-and-path-to-production)
17. [Project structure](#17-project-structure)
18. [Team and AI-assistance disclosure](#18-team-and-ai-assistance-disclosure)

---

## 1. Project overview

**Problem.** Scam victims send money in seconds and cannot reverse the transfer. A typical case: someone calls and says "I sent you 5,000 Tk by mistake, please return it." The victim sends the money back to a different account, and the original deposit later turns out to be fraudulent. Existing defenses are static rules (amount limits, blacklists) that fraudsters learn to dodge.

**Solution.** Before confirmation, Safe-Send scores the transfer and responds by risk level:

| Risk tier | What the sender sees | System action |
|---|---|---|
| Low | Nothing extra | Transfer proceeds |
| Medium | Warning with the main reasons | Sender can proceed or cancel |
| High | Warning, 30-second cool-off, "Report this recipient" | Sender decides after the cool-off |
| Extreme | "Paused for review" | Case goes to an investigator, who releases or rejects it |

Example reasons shown to a sender: *"You are sending back money you just received, but to a different account than it came from."*, *"The recipient account is only 2 days old."*, *"This account received money from 6 different people in the last hour."*

**Users.** Everyday senders (especially less tech-savvy ones) and fraud investigators.

**Problem statement.** For everyday wallet senders, scam transfers cause irreversible money loss within seconds. We built Safe-Send, an AI-powered pre-confirmation risk check that uses transaction, account-behavior and sender-recipient network signals to score each transfer in real time, warn the sender with plain-language reasons, and escalate the riskiest cases to a human investigator, with success measured by the share of scam transactions warned or delayed at a low false-positive rate on legitimate transfers.

---

## 2. Features and how AI is used

### Features
- Real-time risk scoring before confirmation (about 4 ms per request, target 200 ms).
- Four-tier response with plain-language reasons in **English and Bangla**.
- Cool-off timer **enforced on the server**, and a "Report this recipient" option. Three reports on one recipient raise its tier automatically.
- Investigator queue with case detail, SHAP reasons, and a **transaction-network view** (senders, payouts, related accounts, shared devices).
- Human decisions (release or reject) with an audit trail. A rejection flags the recipient for future transfers.
- Business rules separate from the model (very large transfers always get at least a cool-off).
- Access control on investigator endpoints (API key).
- Monitoring endpoint: request counts, tier counts, latency percentiles, open cases.

### AI components

| Component | Method | Role |
|---|---|---|
| Risk detection | **LightGBM** gradient-boosted classifier on 32 features | Produces the risk score |
| Behavioral and network features | Per-sender history, recipient fan-in (distinct senders over time), in/out balance, cash-out history, shared devices | Capture scam patterns rules miss |
| Explanation | **SHAP** attribution, grouped into 9 reason types and rendered with **fixed templates** | Tells the sender and investigator why |
| Network analysis | **NetworkX** graph analytics (ego graph, shared-sender peers, similar-pattern accounts, PageRank, connected components) | Helps investigators see related accounts |
| Robustness | Evasion stress test and adversarial retraining | Checks behavior against adaptive fraudsters |

**No large language model is used in any decision or explanation.** Explanation text comes from fixed templates filled with real feature values, and a reason is shown only if its condition holds in the data (this is tested). This keeps sensitive logic out of free-form prompts.

---

## 3. Results

All results use **synthetic data** with a chronological train / validation / test split. Thresholds were chosen on validation and never on test. Full details, confidence intervals, and figures: [`reports/evaluation.md`](reports/evaluation.md).

| Test set (14,018 transfers, 100 scams) | Static rules | Safe-Send model |
|---|---|---|
| Recall (scams warned) | 57.0% | 95.0% |
| False-positive rate (legitimate transfers warned) | 3.6% | 0.7% |
| Precision | 10.3% | 50.8% |
| Recall at the same alert volume | 57.0% | 100% |

| Scam pattern | Rules | Model |
|---|---|---|
| Mule fan-in | 24% | 100% |
| Mistaken-transfer return scam | 68% | 80% |
| Account takeover | 91% | 100% |
| Amount splitting | 100% | 100% |

- **Fairness:** false-positive rates are 0.2% to 0.9% across regions and 0.6% to 0.8% across value bands; confidence intervals overlap.
- **Evasion stress test:** against adaptive fraudsters the original model's recall drops to 88.7% (partial return scams fall hardest, 80% to 40%). Retraining with the new cases restores it, but the retrained result is optimistic because it is tested on the same evasion strategy.
- **Investigator workload:** about 13 cases per 10,000 transfers.
- **Latency:** p95 about 4 ms per scoring request.
- **Simulated loss prevented:** 47.5% of scam value under stated behavioral assumptions (19.7% if senders ignore every warning, from holds alone). This is a simulation, not measured behavior.

---

## 4. Technology stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+, JavaScript (React) |
| Data and features | Pandas, NumPy |
| ML | LightGBM, scikit-learn, SHAP |
| Graph analytics | NetworkX |
| API | FastAPI, Uvicorn, Pydantic |
| Frontend | React with Vite (sender app and investigator dashboard) |
| Testing | pytest, httpx |
| Reporting | matplotlib |
| Deployment | Docker, Hugging Face Spaces |

No external AI API or paid service is required to run the project.

---

## 5. Requirements

- **Python 3.10 or newer** and `pip`
- **Node.js 18 or newer** (only to run or build the frontend)
- **Git**
- About 1 GB of free disk space and 1 GB of RAM (the API uses about 400 MB)
- Docker (optional, for the container build)
- Internet access to install packages

---

## 6. Installation and setup

```bash
git clone https://github.com/protwoy007/safe-send.git
cd safe-send

# 1. Python dependencies
python -m pip install -r requirements.txt

# 2. Generate synthetic data, build features, train the model (same seed gives the same data)
python -m src.data_gen.generate --out data --seed 42
python -m src.features.build --data data --out data/features.csv
python -m src.models.train --data data

# 3. Frontend dependencies (if you want to run the web app)
cd frontend && npm install && cd ..
```

Data files (`data/*.csv`) and the trained model (`models/risk_model.pkl`) are not stored in Git. The three commands in step 2 recreate them in about a minute.

---

## 7. Environment variables

Copy `.env.example` to `.env` for local use. **Never commit real secrets.** Use placeholders in the repository.

| Variable | Purpose | Default / example |
|---|---|---|
| `INVESTIGATOR_API_KEY` | Secret key required in the `X-API-Key` header for investigator endpoints. If unset, those endpoints always return 401. | `change-me-before-deploy` (placeholder; choose a strong value) |
| `MODEL_PATH` | Location of the trained model | `models/risk_model.pkl` |
| `DATA_DIR` | Folder with generated data and features | `data` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins for local frontend development | `http://localhost:5173` |
| `FRONTEND_DIST` | Folder with the built frontend that the API serves | `frontend/dist` |
| `EAGER_LOAD` | Load model and history at start-up (`1`) or on the first request (`0`) | `1` |
| `VITE_API_URL` | (Frontend, local development only) address of the API | `http://localhost:8000` |

For the deployed app, `INVESTIGATOR_API_KEY` is stored as a Hugging Face Space secret.

---

## 8. Run and build commands

**Run the API (development)**
```bash
export INVESTIGATOR_API_KEY=your-own-key        # Windows PowerShell: $env:INVESTIGATOR_API_KEY="your-own-key"
python -m uvicorn src.api.main:app --port 8000
```
Open `http://localhost:8000/docs` for interactive API documentation.

**Run the frontend (development)**
```bash
cd frontend
npm run dev                                     # http://localhost:5173
```

**Build the frontend and serve everything from one URL**
```bash
cd frontend && npm run build && cd ..
python -m uvicorn src.api.main:app --port 8000   # now serves the app at http://localhost:8000
```

**Docker (same as the deployed image)**
```bash
docker build -t safe-send .
docker run -p 7860:7860 -e INVESTIGATOR_API_KEY=your-own-key safe-send
```
The image generates the data and trains the model during the build. Open `http://localhost:7860`.

**Evaluation report and latency benchmark**
```bash
python -m src.evaluation.report --data data      # writes reports/evaluation.md and figures
python scripts/benchmark_latency.py --n 300      # p50 / p95 / p99 scoring latency
```

**Show example explanations**
```bash
python -m src.explain.reasons --data data --lang en     # or --lang bn
```

---

## 9. Live deployment

- **Live URL:** `https://<your-username>-safe-send.hf.space`
- Hosted on a Hugging Face Space (Docker). To redeploy: `bash scripts/deploy_hf.sh` (one-time setup: `git remote add space https://huggingface.co/spaces/<your-username>/safe-send`).
- Judges can try the **demo scenarios** in the sender app (normal payment, genuine return, return scam, mule account, account takeover, split drain, false alarm).
- For the investigator dashboard (`/investigator`), enter the investigator key supplied to the judges with the submission.
- Free Spaces sleep after inactivity. The first request after a long idle period can take a minute.
- Cases and reports are kept in memory and reset when the Space restarts. This is a prototype.

---

## 10. Testing instructions

```bash
python -m pytest -q          # expect: 33 passed
```

What the tests cover:
- **Data generator:** schema, scam rate, all patterns present, accounts exist before use, deterministic output.
- **Features:** no future leakage (features recomputed from only earlier rows are identical), return-to-original-sender cue, chronological split.
- **Explanations:** structure, reasons only when conditions hold, Bangla output.
- **API:** validation, server-enforced cool-off, held transfers cannot be pushed through by the sender, investigator authentication, report-driven escalation, **no training/serving skew** (live features equal batch features), latency.
- **Network view:** ring and shared-device detection, past-only data, authentication, no ground-truth labels in output.
- **Evaluation:** confidence intervals, policy rule only raises tiers, simulation behavior, evasive generator.
- **Static serving:** single-page-app routes and path-traversal protection.

**Manual check (about 2 minutes):** start the API, open `/docs`, call `POST /v1/demo/load/return_scam`, send the returned body to `POST /v1/score`, and confirm a medium or higher tier with the reason "You are sending back money you just received...".

---

## 11. API reference

Interactive documentation: `/docs`.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/v1/score` | Score a transfer before confirmation | none |
| POST | `/v1/confirm` | Proceed or cancel (cool-off enforced; held transfers refused) | none |
| POST | `/v1/report` | Report a recipient | none |
| GET | `/v1/transfers/{tx_ref}` | Transfer status | none |
| GET | `/v1/metrics` | Request, tier, latency and case counts | none |
| GET | `/v1/demo/examples`, POST `/v1/demo/load/{id}` | Ready demo scenarios | none |
| GET | `/v1/cases` | Investigator queue | `X-API-Key` |
| GET | `/v1/cases/{id}` | Case detail | `X-API-Key` |
| GET | `/v1/cases/{id}/network` | Transaction-network view | `X-API-Key` |
| POST | `/v1/cases/{id}/decision` | Release or reject a held transfer | `X-API-Key` |

Example response (abridged):
```json
{
  "tx_ref": "T3fa9c1d2e0", "risk_score": 0.93, "tier": "high", "action": "warn_cooloff",
  "cooloff_seconds": 30,
  "message": "High risk. Please wait 30 seconds before confirming. You can report this recipient.",
  "reasons": [
    {"code": "RETURN", "text": "You are sending back money you just received, but to a different account than it came from.", "impact": 2.36}
  ],
  "can_report": true, "case_id": null, "status": "ready"
}
```

---

## 12. Architecture

```
Synthetic data -> Feature store (past-only state) -> LightGBM risk score
   -> SHAP reasons + fixed templates -> Business rules (can only raise a tier)
   -> Sender warning / cool-off / investigator queue -> Human decision -> Feedback
```

- **One feature implementation** (`FeatureStore`) is used for training and for the live API, so there is no training/serving skew.
- **Rules are separate from the model** (`src/rules/policy.py`). The model supplies a score; rules and thresholds decide the action.
- **Explanations are traceable:** score, evidence (feature values), and generated text are returned separately.
- **Production path:** replace the in-memory state with a feature store, database and message queue; keep the API contract; retrain with investigator-confirmed cases; run a controlled warning experiment before any rollout.

---

## 13. Synthetic data

No production data is used. Generated by `src/data_gen/generate.py` (about 75,000 transfers, 3,300 wallets, 60 days, seed 42). Every assumption is documented in the generator's docstring and configuration.

**Normal behavior:** regular contacts, merchant payments, weekly and month-end patterns, occasional large legitimate transfers.

**Injected scam patterns:** mule rings (fan-in then cash-out), mistaken-transfer return scams, account takeover, amount splitting below the rule limit.

**Legitimate look-alikes** (so the model cannot learn shortcuts): new wallets receiving family money, new-merchant opening-day bursts, new wallets with legitimate fan-in, large transfers from a new device, genuine returns to the original sender.

**Labels:** `is_scam = 1` only for transfers a sender is tricked or forced into. Columns starting with `gt_` are ground truth for evaluation only and are never features. A separate evasive world (`src/evaluation/evasion.py`) tests adaptive fraudsters.

---

## 14. Responsible AI and security

| Principle | How Safe-Send addresses it |
|---|---|
| Privacy | Synthetic data only; no personal information anywhere |
| Explainability | SHAP reasons shown to sender and investigator; tested for consistency with data |
| Fairness | False-positive rates reported by value band, account age and region with confidence intervals |
| Security | Server-side cool-off, API-key access control (constant-time comparison), input validation, no secrets in the repository, text generated only from templates (no prompt-injection surface in the decision path) |
| Human oversight | Only an investigator can release or reject a held transfer |
| Transparency | Score, evidence, rules triggered and generated text are returned separately; limitations stated openly |
| No harmful automation | No auto-block; the most severe outcome is a hold decided by a person; rules can only raise a tier |

---

## 15. Other configuration

- **CORS:** local frontend development origin is set by `ALLOWED_ORIGINS`. The deployed app serves frontend and API from the same origin.
- **Investigator access:** the key is held in memory in the dashboard and never stored in the repository or browser storage.
- **Hugging Face deployment:** needs a Space (SDK Docker), the `INVESTIGATOR_API_KEY` secret, and the `space` Git remote described above.
- **Windows:** use Git Bash for the shell commands, or set variables with PowerShell. LF/CRLF warnings from Git are harmless.
- **Line of authority for tiers:** thresholds are saved in `models/thresholds.json`, set on validation by false-positive budget (medium 1.5%, high 0.4%, extreme 0.1% of legitimate transfers).

---

## 16. Limitations and path to production

**Limitations**
- Synthetic data: results show the method works, not real-world accuracy.
- The test set has 100 scams, so per-pattern and per-group numbers have wide confidence intervals.
- Warning-effect and loss-prevented figures rest on stated assumptions.
- The retrained (hardened) model is tested on the same evasion strategy it learned; real fraudsters will adapt again.
- Some reasons describe the recipient (for example earlier cash-outs), which a sender cannot verify; the system treats them as evidence, not proof.
- State is in memory; there is no persistent database.

**Path to production**
1. Controlled validation on governed, anonymized upay data.
2. Replace in-memory state with a feature store, database and queue.
3. Real-user experiment on warning effectiveness, with the false-positive budget as a guardrail.
4. Monitoring for drift and fairness; retraining with investigator-confirmed cases.
5. Security and privacy review before any integration.

---

## 17. Project structure

```
safe-send/
├── src/
│   ├── data_gen/generate.py      synthetic network and scam patterns
│   ├── features/build.py         32 past-only features, FeatureStore, chronological split
│   ├── models/train.py           static-rule baseline, LightGBM, evaluation
│   ├── explain/reasons.py        SHAP reasons, fixed English/Bangla templates
│   ├── rules/policy.py           business rules (separate from the model)
│   ├── api/                      FastAPI app, engine, NetworkX network view
│   └── evaluation/               report, fairness, evasion stress test, simulation
├── frontend/                     React app: sender flow and investigator dashboard
├── tests/                        33 automated tests
├── scripts/                      latency benchmark, deploy script
├── reports/                      evaluation report and figures
├── deploy/                       Hugging Face Space README
├── Dockerfile
└── requirements.txt
```

---

## 18. Team and AI-assistance disclosure

**Team:** `<names and roles>`

**AI assistance:** parts of the code and documentation were produced with the help of an AI assistant (Claude, Anthropic). The team reviewed, tested and understands the submitted work and can explain its design, implementation and AI components. The ML models are open-source libraries (LightGBM, SHAP, NetworkX); no external AI service is called at run time.

Built for AI Dev Fest 2026, organized by DIU CPC with upay.
