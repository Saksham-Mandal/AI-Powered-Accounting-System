# EZPrntz Accounting System

An internal accounting and business analytics platform for EZPrntz, an e-commerce poster business.

The project combines a React frontend, a FastAPI backend, SQLite storage, CSV importing, double-entry journal posting, and financial reporting groundwork.

## Features

- Import Etsy statement CSV rows into SQLite
- Seed a chart of accounts
- Convert Etsy transactions into balanced journal entries
- View live journal entries and raw Etsy rows in the frontend
- Multi-page accounting UI for dashboard, income statement, balance sheet, transactions, and imports

## Tech Stack

- React
- TypeScript
- Vite
- Python
- FastAPI
- SQLite

## Backend Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Initialize and seed local data:

```bash
python3 backend/db/initdb.py
python3 backend/csv_parser.py
python3 backend/db/account_chart.py
python3 backend/post_transacs.py
```

Run the API:

```bash
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies `/api` requests to the FastAPI server at `http://127.0.0.1:8000`.

## Notes

Local SQLite databases, virtual environments, build artifacts, dependency folders, and real CSV exports are intentionally ignored by Git.
