# AI Sales Intelligence

A full-stack business analytics application that imports sales transactions, visualizes revenue, segments customers, and compares repeat-purchase classifiers.

Independent portfolio project built with React, TypeScript, FastAPI, SQLite, Pandas, and scikit-learn. The included dataset is synthetic.

## Features

- CSV and Excel (.xlsx) imports with whole-file validation.
- Transactional order updates keyed by order ID.
- Import history showing added, updated, and unchanged orders.
- Revenue, order count, customer count, and average order value.
- Monthly revenue bar and line charts with date filters.
- Customer segment chart, search, filters, spend sorting, and CSV export.
- Responsive layout with light and dark themes.
- Temporal model comparison: majority baseline, logistic regression, and random forest.

## Architecture

React dashboard → FastAPI JSON API → SQLite transaction storage.

Pandas builds historical customer features. Scikit-learn trains and evaluates classifiers on the backend. The frontend displays results.

## Quick start

Requirements: Python 3.12 and Node.js 22. The repository includes a Codespaces development-container configuration.

Backend, from the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --only-binary=:all: -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend, in another terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Open port 5173 for the dashboard. API documentation is available at /docs on port 8000. Vite proxies /api requests to the backend.

Upload backend/sample_sales.csv, explore the charts, and select Compare models.

On Windows PowerShell, activate the environment with .venv\Scripts\Activate.ps1 from the backend directory.

## Input data

Required columns:

```csv
order_id,customer_id,order_date,amount
ORD-001,C001,2025-01-05,150.00
```

Dates use YYYY-MM-DD. Amounts must be positive and below 1,000,000,000. IDs must be nonempty; duplicate order IDs within one file are rejected. Files must be no larger than 2 MB. Excel imports read the first worksheet.

Uploads combine with stored orders. Re-uploading an existing order ID updates that order. Invalid files leave existing orders unchanged. Extra input columns are currently ignored; they are not stored or modeled. All amounts are assumed to share one currency.

Revenue filters affect the metric cards and revenue chart. Segments and model comparison use all stored orders.

## Database

SQLite persists local orders in backend/sales.db, created automatically on first database access. Set SALES_DB to override its location.

backend/db/schema.sql documents the orders and uploads tables. The database file is excluded from Git; the schema and synthetic CSV reproduce the demo without distributing stored user data.

## Customer segmentation

Recency is days since the last order, measured at the latest dataset date. Frequency is total orders. Monetary value is total spend.

At risk: recency exceeds 60 days. Loyal: remaining customers with at least four orders. Active: remaining customers. These are business heuristics, not clustering results.

## Model comparison

Target: whether an existing customer purchases in the next calendar month. Features use only orders on or before each monthly cutoff.

Earlier cutoffs train candidate models. A later cutoff selects a candidate using validation F1. The selected candidate is refit on training plus validation and evaluated on a separate final test cutoff alongside a refit majority baseline.

Candidates are logistic regression with training-fitted scaling and random forest, plus the majority baseline. The baseline can be selected if it performs best. Accuracy, positive-class precision, recall, and F1 are reported.

At least six calendar months and sufficient examples from both classes are required. The newest month is excluded because it may be incomplete. Earlier months are assumed fully observed; transaction dates alone cannot verify source completeness.

The comparison is manually triggered and does not save or deploy a production model. Repeated tuning against the final test period would compromise its independence. Synthetic scores do not establish real-world business impact.

## API

| Endpoint | Purpose |
| --- | --- |
| POST /api/upload | Validate and import CSV or Excel |
| GET /api/summary | Revenue metrics; optional start and end dates |
| GET /api/segments | RFM customer summaries |
| GET /api/uploads | Latest 20 successful imports |
| POST /api/compare-models | Temporal model selection and evaluation |
| GET /api/model-report | Original logistic regression experiment |

## Verification

```bash
cd backend
python -m pytest -q
```

From the frontend directory:

```bash
npx tsc --noEmit
npm run build
```

Tests cover import atomicity, repeat-upload behavior, Excel ingestion, import counts, date filters, and temporal comparison.

## Scope

Designed for modest datasets and local demonstrations. Customer pagination runs in the browser, and analytics read stored orders into memory. Authentication, background training, persisted model versions, production deployment, and PostgreSQL integration are not implemented.

No paid model API or credentials are required. Use synthetic or appropriately anonymized data for public demonstrations.
