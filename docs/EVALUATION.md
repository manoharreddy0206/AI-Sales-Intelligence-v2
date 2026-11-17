# Evaluation notes

All data is synthetic. Results below come from GitHub Actions (pinned `backend/requirements.txt` on Python 3.12, Ubuntu) and from the live Render deployment, both on **2026-11-17**, unless a section says otherwise.

## What has been verified

| Item | Where | Result |
| --- | --- | --- |
| Backend pytest, including the three FastAPI `TestClient` modules (`test_api.py`, `test_v2.py`, `test_api_copilot.py`) | GitHub Actions | **46 passed, 0 failed, 0 skipped** in 2.8 s. CI fails the build if any test is skipped. |
| Copilot eval, stub provider | GitHub Actions | **24/24** cases, numeric 12/12, citations 6/6 |
| Frontend `npx tsc --noEmit` and `npm run build` (Vite 6.4.6) | GitHub Actions | Pass. `npm audit` reports 0 vulnerabilities. |
| Docker image in `DEMO_MODE=1` | GitHub Actions | Builds; `scripts/smoke_test.py` passes; `POST /api/upload` returns 403 |
| Live demo, https://ai-sales-intelligence-bzg4.onrender.com | From a workstation | `smoke_test.py` **6/6**: health, config, 269 orders, copilot revenue equals dashboard revenue (July 2025, 5,722.58), frontend at `/`, API docs at `/docs`. Upload returns 403. |
| Copilot against a real LLM (Anthropic) | n/a | **Pending.** No API key configured yet. |

CI results are published as annotations on each run, so anyone can read them on the Actions page without signing in.

## Import checks (`tests/test_ingest.py`)

| Step | Input rows | Accepted | Added / updated / unchanged | Unique orders stored | Stored revenue |
| --- | --- | --- | --- | --- | --- |
| `sample_sales.csv` | 269 | 269 | 269 / 0 / 0 | 269 | 54,233.70 |
| `sample_updates.csv` | 20 | 20 | 5 / 10 / 5 | 274 | 54,848.70 |
| `sample_invalid.csv` | 5 | 0 (rejected at CSV line 6) | n/a | 274 | 54,848.70 |
| Fault injection: the DB aborts on row 3 after rows 1 and 2 (one new, one update) were written | 3 | 0 | n/a | 269 (unchanged) | unchanged; the updated order keeps its old amount |

Handling rules:

- **Dates** must be ISO `YYYY-MM-DD`. Python's `date.fromisoformat` also accepts compact ISO forms such as `20250105`, which are normalised to `2025-01-05`. That was already true in v2 and is noted here rather than changed.
- **Excel.** Real date cells are accepted. Text dates follow the CSV rule (see the engineering story).
- **Money** is a plain number with 0 < amount < 1e9. `$100` and `"1,200"` are rejected, and no currency is stored.
- **Duplicates.** The same order ID twice in one file rejects the file. An order ID already in the database is updated in place.
- **Partially invalid files** are rejected as a whole, and the error names the first bad line.

## Copilot eval (`python -m eval.run_eval`)

The cases are in 24 questions in `backend/eval/questions.jsonl`. Ground truth is SQL written inside the eval script, separate from `app.analytics`, and every numeric answer is also compared with the dashboard's `summary()` for the same range.

| Category | Cases | Stub provider result |
| --- | --- | --- |
| Totals (month, month name + year, range, dashboard filter, partial month, AOV, order count) | 7 | 7/7 |
| Comparisons, including a zero denominator (percent reported as not defined) | 3 | 3/3 |
| Ambiguous dates (month without year, "recently", filter not set) | 3 | 3/3 (clarifying question) |
| Empty period and empty dataset | 2 | 2/2 |
| Definitions with citation, and a missing entry with no citation | 5 | 5/5 |
| Provider down, provider fails after a tool call, tool crash | 3 | 3/3 (explicit error, fetched figures kept) |
| Glossary passage containing injected instructions, followed by a `run_sql` call | 1 | 1/1 (call refused, row count unchanged, citation kept) |
| **Total** | **24** | **24/24**. Numeric 12/12, citations 6/6. |

Latency in CI: median 1.0 ms, p95 3 ms. This is in-process with no network or LLM, so it says nothing about real-model latency. On the live demo, stub answers took 3 to 5 ms server-side. CI uploads the raw JSON as the `backend-reports` artifact, and an earlier local run is checked in at `backend/eval/results/2026-11-17-stub.json`.

**What the stub run measures.** It tests the tool layer, period resolution, the agreement between dashboard and copilot, citations, the numeric guard and fault handling. The stub picks tools with keyword rules, so it does **not** measure how well a real model chooses tools or phrases answers. To get those numbers, run `python -m eval.run_eval --provider anthropic` with a key, then record the pass counts and latency from `eval/results/<date>-anthropic.json`.

**Issue the eval found.** On the first run, 23/24 passed. *How are sales doing recently?* was routed to the glossary, because the stub treated "how are" as a definition question. The stub's definition rule now requires a verb such as *defined*, *mean* or *calculated*. The fix applies only to the stub and doesn't touch the hosted LLM path.

## Classifier (`python -m eval.classifier_report`)

These figures come from an earlier run with Python 3.13, pandas 3.0.5 and scikit-learn 1.9.1, not from the pinned versions (pandas 2.2.3, scikit-learn 1.6.1), so small numeric differences are possible. CI runs the classifier's unit tests, including the leakage check, but not this report.

| Item | Value |
| --- | --- |
| Split | train cutoffs 2025-01..04 (240 rows), validation 2025-05 (60), test 2025-06 (60) |
| Picked by validation F1 | Majority baseline (0.652 vs random forest 0.613, logistic regression 0.576) |
| Test repeat-buyer F1, picked model (the baseline) | 0.636 |
| Test F1, majority baseline | 0.636 |
| Test positive rate | 46.7%. Predicting everyone as a repeat buyer gives F1 2p/(1+p) = 0.636. |
| Diagnostic only, not used for selection: test F1 of each candidate refit on train + validation | baseline 0.636 · logistic regression 0.629 · random forest 0.483 |
| Leakage check | `test_features_only_use_orders_available_at_the_cutoff`: features computed from the full data equal features computed from data truncated at each cutoff |

Interpretation: on this synthetic data, the learned models don't beat the majority baseline on repeat-buyer F1. The data is small (60 customers per cutoff), and the generator draws purchases independently each month. Validation picking the baseline is the honest outcome of the procedure. I didn't tune against the test cutoff.
