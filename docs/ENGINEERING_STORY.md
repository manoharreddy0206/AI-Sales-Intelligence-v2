# Engineering story

Live demo: **https://ai-sales-intelligence-bzg4.onrender.com**

The public demo loads **269 synthetic orders** (60 customers, 1 Jan to 23 Aug 2025), **blocks uploads** (`POST /api/upload` returns 403), and runs the copilot in **stub mode**: a labelled, rule-based provider with no language model. Every answer carries an orange *Stub mode · no LLM* badge.

## 90-second demo script

Open the live URL before the call. The free Render instance sleeps when idle, and the first request can take about 50 seconds to wake it.

| Time | Show | Say | File to open if asked |
| --- | --- | --- | --- |
| 0:00 | Dashboard header and the demo banner | "A sales dashboard for someone with an order export and no data team. This public copy is seeded with 269 synthetic orders, and uploads are switched off." | [backend/app/main.py](../backend/app/main.py) (`DEMO_MODE`, `lifespan`, `upload`) |
| 0:10 | Cards: revenue 54,233.7, 269 orders, 60 customers, average 201.61. Then the monthly chart. | "Every figure is a parameterized SQL query over SQLite. The same function feeds the cards and the copilot." | [backend/app/analytics.py](../backend/app/analytics.py) (`summary`) |
| 0:25 | Copilot: click *What was revenue last month?* | "The backend resolves 'last month' from the data, not from today's date, so it's July 2025. The table comes from the tool result, not from model text: 5,722.58 from 29 orders, which matches the July bar." | [backend/app/copilot/tools.py](../backend/app/copilot/tools.py) (`get_revenue_summary`) |
| 0:40 | Click *What changed versus the previous month?* | "The backend computes the deltas. If the earlier month were empty, the percent change would say 'not defined' rather than infinity." | [backend/app/copilot/tools.py](../backend/app/copilot/tools.py) (`compare_periods`) |
| 0:50 | Click *How is a repeat customer defined?* | "Definitions are retrieved from a glossary in the repo and cited by ID. Each entry also points to the code that implements it." | [backend/glossary/metrics_glossary.md](../backend/glossary/metrics_glossary.md) |
| 1:00 | Point at the orange badge | "This is stub mode. With an Anthropic key, Claude chooses the tools through the Messages API, but it still can't produce the figures itself." | [backend/app/copilot/provider.py](../backend/app/copilot/provider.py), [backend/app/copilot/service.py](../backend/app/copilot/service.py) |
| 1:10 | GitHub: the Excel regression test | "A real bug I found: an Excel text date, 03/04/2025, was silently stored as 4 March. Here's the test that pins the fix." | [backend/tests/test_ingest.py](../backend/tests/test_ingest.py) (`test_excel_text_dates_follow_the_csv_rule`) |
| 1:20 | GitHub Actions: the latest green run | "CI runs the unit and HTTP tests, a 24-case copilot eval, the frontend build and a Docker smoke test on every push." | [.github/workflows/ci.yml](../.github/workflows/ci.yml), [backend/eval/questions.jsonl](../backend/eval/questions.jsonl) |

**If they want to see uploads**, run it locally (see the README quick start). Upload `backend/sample_sales.csv`, then `sample_updates.csv` (5 added, 10 updated, 5 unchanged), then `sample_invalid.csv`, which is rejected at line 6 with nothing stored.

## Request flow

The browser posts the question to `POST /api/copilot`. [service.py](../backend/app/copilot/service.py) sends it to the provider together with three tool schemas. The provider picks a tool and passes a period token such as `last_month`. The backend validates the input with Pydantic and resolves the token to exact dates, anchored to the dataset's latest order. It then calls `analytics.summary`, the function behind the dashboard cards. The tool result goes back to the provider so it can write one sentence. The response contains that sentence, the raw tool payload, any glossary citations, the dataset scope, a request ID and the elapsed time. The UI renders the numbers from the payload.

**Design choice.** The model decides *what* to look up and explains the result, but it never produces the figures. Totals come from queries, definitions come from a checked-in glossary with stable IDs, and date arithmetic happens in Python. A guard flags any number in the model's sentence that doesn't match a tool value.

**Tradeoff.** The copilot can only answer what three tools cover, so open-ended questions get a clarifying question or a refusal. In return, every number can be checked against SQL. Retrieval is keyword-based rather than embeddings: the glossary has 12 entries, keyword search found the right entry for every eval question, and there is no vector store to deploy.

## Anthropic integration

- **Provider.** [provider.py](../backend/app/copilot/provider.py) `AnthropicProvider` calls the Anthropic Messages API (`/v1/messages`, `anthropic-version: 2023-06-01`) with tool definitions. It uses only the standard-library HTTP client, so there is no SDK dependency. The default model is `claude-haiku-5-5`, and `COPILOT_MODEL` overrides it.
- **Selection.** `_provider()` in [service.py](../backend/app/copilot/service.py) uses Anthropic when `ANTHROPIC_API_KEY` is set, and the stub otherwise. Setting `COPILOT_PROVIDER=stub` forces stub mode. The key is read on the server only and never reaches the browser.
- **Stub provider.** `StubProvider` emits the same `tool_use` and `text` blocks as the real API, so the same tool loop, validation, guards and UI run without a key. The UI labels it on every answer.
- **Limits.** Each question gets at most 4 tool calls and 4 model turns, a 20 s provider timeout and a 30 s overall deadline. Questions are capped at 500 characters, and demo mode allows 30 questions per client per 10 minutes. On a provider error, the API returns an explicit message plus any figures already fetched. Error bodies aren't echoed back, because they can contain request content.
- **Status: real-model evaluation is pending.** The same 24-case eval runs against Claude with `python -m eval.run_eval --provider anthropic`, but it hasn't been run yet, because no API key has been configured for this project. Every copilot result reported so far uses the stub provider. The stub measures the tools, period resolution, citations, guards and fault handling. It does not measure how well a model chooses tools or phrases answers.

## The Excel date bug and its regression test

**Where it came from.** I found it while writing date-handling checks across the CSV and Excel import paths for the hosted demo. The bug was already in the v2 code.

| | |
| --- | --- |
| Input | [backend/tests/fixtures/ambiguous_text_date.xlsx](../backend/tests/fixtures/ambiguous_text_date.xlsx): one row, `order_id=X1, customer_id=C1, order_date="03/04/2025"` stored as a **text** cell (common in day-first exports), `amount=10` |
| Expected | Rejection. The import contract says dates are `YYYY-MM-DD`, and the CSV path already rejects `03/04/2025`. |
| Observed in v2 | The file was accepted and the order was stored as **2025-03-04** (4 March). A user who meant 3 April got that revenue in the wrong month, with no error. |
| Cause | The Excel branch ran `pd.to_datetime(...)` over the whole `order_date` column, and pandas inferred a month-first format from the first value. Adding a second row with `13/04/2025` made the whole file fail instead, so the outcome depended on which rows happened to be present. The CSV path used `date.fromisoformat`, so the two paths applied different rules to the same field. |
| Fix | [`ingest._excel_date_cell`](../backend/app/ingest.py) converts each cell on its own. Real Excel date cells arrive as datetimes and are unambiguous, so they become ISO dates. Text cells pass through unchanged into the same validator the CSV path uses. |
| Regression tests | [backend/tests/test_ingest.py](../backend/tests/test_ingest.py): `test_excel_text_dates_follow_the_csv_rule` and `test_excel_real_date_cells_and_iso_text_are_accepted`. Both run in CI on every push. |

```python
def test_excel_text_dates_follow_the_csv_rule():
    # Regression: v2 parsed the text "03/04/2025" as 2025-03-04 (month-first) and stored it.
    raw = xlsx([{"order_id": "X1", "customer_id": "C1", "order_date": "03/04/2025", "amount": 10}])
    with pytest.raises(ingest.UploadError, match="line 2"):
        ingest.parse_upload("orders.xlsx", raw)
```

The companion test checks that the fix didn't overcorrect: a real date cell `datetime(2025, 4, 3)` imports as `2025-04-03`, and ISO text `2025-04-05` still imports. Running the old Excel logic against the same input stores `2025-03-04`, so the first test fails on the v2 behaviour.

**Why it matters for the copilot.** "What was revenue last month?" is only as right as the stored dates. A silent day/month swap moves revenue between months, and the dashboard and the copilot would both report the wrong figure while agreeing with each other. A consistency check between them can't catch that; only a test on the input path can.

## A related decision: what "last month" means

The sample data ends on 2025-08-23. Measured from today's date, "last month" would land in 2026 and return zero orders. Relative periods therefore anchor to the dataset's latest order date, the same anchor the segment panel uses for recency. So "last month" means July 2025, and every answer states the resolved range and the anchor date. The tradeoff: on a dataset updated daily, "last month" follows the data rather than the calendar. This is documented in the glossary entry `[relative-periods]`.

All data in this project is synthetic. The fault-injection check (a failure mid-import followed by a full rollback) uses a SQLite trigger that aborts on a chosen row; it is not a real crash.
