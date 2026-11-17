# Engineering story

## Interview walkthrough (about 2 minutes)

**User problem.** A small-business analyst has an export of orders and wants answers, not a BI tool. They need to know what revenue was last month and what changed, and they need to trust the numbers enough to forward them.

**Request flow.** The browser posts the question to `POST /api/copilot`. The backend sends it to the LLM with three tool definitions. The model picks a tool and passes a period token such as `last_month`. The backend validates the input and resolves the token to exact dates, anchored to the dataset's latest order rather than today. It then calls `analytics.summary`, the same function behind the dashboard cards, which runs a parameterized SQL range query. The tool result goes back to the model so it can write one sentence. The API response contains the sentence, the raw tool payload, any glossary citations, the dataset scope, a request ID and the elapsed time. The UI draws the numbers from the payload.

**Design choice.** The LLM chooses *what* to look up and explains it, but it never produces the figures. Totals come from queries, definitions come from a checked-in glossary with stable IDs, and date arithmetic happens in Python. A guard flags any number in the model's sentence that doesn't match a tool value.

**Tradeoff.** The copilot can only answer what the three tools cover, so open-ended questions get a clarifying question or a polite refusal. In exchange, every number is checkable and an eval can compare it with SQL. I also chose keyword retrieval over embeddings. The glossary has 12 entries, keyword search found the right entry for every eval question, and it adds no vector store to deploy. I'd add embeddings only if an eval showed keyword search missing paraphrases.

## A real bug: Excel text dates were silently reinterpreted

**Where it came from.** I was writing date-handling checks across the CSV and Excel import paths for the hosted demo. This bug was in the v2 code as uploaded. I didn't introduce it.

| | |
| --- | --- |
| Input | `backend/tests/fixtures/ambiguous_text_date.xlsx`: one row, `order_id=X1, customer_id=C1, order_date="03/04/2025"` (a text cell, the way many day-first exports in India store dates), `amount=10` |
| Expected | Rejection. The README contract says dates are `YYYY-MM-DD`, and the CSV path rejects `03/04/2025`. |
| Observed (v2) | The file was accepted and the order was stored as **2025-03-04** (4 March). A user who meant 3 April gets revenue in the wrong month, with no error shown. |
| Investigation | The Excel branch ran `pd.to_datetime(frame["order_date"], errors="raise")` on the whole column. Pandas inferred a month-first format from the first value. A second row with `13/04/2025` made the whole file fail with a format error, so the behaviour depended on which rows happened to be present. The CSV path uses `date.fromisoformat`, so the two paths applied different rules to the same field. |
| Fix | `ingest._excel_date_cell` converts each cell on its own. Real Excel date cells, which arrive as datetimes and are unambiguous, become ISO dates. Text cells pass through unchanged into the same validator the CSV path uses. |
| Verification | `test_excel_text_dates_follow_the_csv_rule` now gets `UploadError: Invalid data at CSV line 2`. `test_excel_real_date_cells_and_iso_text_are_accepted` shows real date cells and ISO text still import. Running the old Excel logic against the same fixture still stores `2025-03-04`, so the test does catch the v2 behaviour. |

**Why it matters for the copilot.** "What was revenue last month?" is only as right as the stored dates. A silent day/month swap would move revenue between months, and the dashboard and the copilot would both report the wrong figure while agreeing with each other.

## A related design decision: what "last month" means

The sample data ends on 2025-08-23. If "last month" were taken from today's date (November 2026), it would resolve to October 2026 and return zero orders, which is a confusing answer for a historical dataset. Instead, relative periods anchor to the dataset's latest order date. This is the same anchor the segment panel already used for recency. So "last month" means July 2025: 5,722.58 revenue from 29 orders, which matches the July bar on the chart. Every answer states the resolved range and the anchor, and the latest month is flagged as partial. The tradeoff: once a live dataset is updated daily, "last month" follows the data rather than the calendar. That's correct for a dashboard, and it is documented in the glossary entry `[relative-periods]`.

All results above come from synthetic data. The fault-injection result (failure mid-import, full rollback) used a SQLite trigger that aborts on a chosen row, and was not a real crash.

## 90-second demo script

1. **0:00.** "This is a sales dashboard for someone with an order export and no data team." Show the empty dashboard.
2. **0:10.** Upload `sample_sales.csv`. "269 orders validated and imported in one transaction." Point at the cards (revenue 54,233.7, 269 orders, 60 customers) and the monthly chart.
3. **0:25.** Upload `sample_updates.csv`. "Re-uploading updates orders by ID: 5 added, 10 updated, 5 unchanged." Upload `sample_invalid.csv`. "One bad row rejects the whole file, so stored data never ends up half-imported."
4. **0:40.** In the copilot, click *What was revenue last month?* "The model picked a typed tool, and the backend resolved 'last month' to July 2025 from the data. This table comes from the tool result, and it matches the July bar." *(If you show this after step 3, the July total includes the updated orders. Show it on fresh sample data to get 5,722.58.)*
5. **0:55.** Click *What changed versus the previous month?* "Revenue, orders and average order value for both months, with deltas computed by the backend. When the previous month is empty, the percent change says 'not defined' instead of infinity."
6. **1:10.** Click *How is a repeat customer defined?* "Definitions come from a glossary in the repo, cited by ID and linked to the code that implements them."
7. **1:20.** "I evaluated it with 24 questions against independent SQL, including failures and a prompt-injection case. The README has the commands and the results."

## Résumé bullets and the evidence behind them

- **Built a React and FastAPI sales intelligence app that validates and imports CSV and Excel orders in one transaction. It imported 269 synthetic transactions, updated existing orders by ID (5 added, 10 updated and 5 unchanged on re-upload), and rejected invalid files without partial writes.**
  Evidence: `backend/tests/test_ingest.py` (`test_sample_then_changed_reupload_then_invalid`, `test_failure_mid_import_rolls_back_everything`) and the import table in `docs/EVALUATION.md`.

- **Added a sales copilot with typed read-only analytics tools and cited retrieval over metric definitions. Verified 12/12 numeric answers against SQL and the dashboard, and 6/6 citations, in a 24-case evaluation that includes provider failures and a prompt-injection case (stub provider; real-LLM run pending).**
  Evidence: `backend/eval/run_eval.py`, `backend/eval/questions.jsonl`, `backend/eval/results/2026-11-17-stub.json` and `backend/tests/test_copilot.py`. Once you run the eval with `--provider anthropic`, replace "stub provider; real-LLM run pending" with the real pass counts and median latency.

Hold off on the word "deployed" until the Render URL passes `scripts/smoke_test.py` from a fresh browser.
