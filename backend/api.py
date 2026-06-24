import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "accounting.db"

app = FastAPI(title="EZPrntz Accounting API")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/transactions/etsy")
def get_etsy_transactions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                transaction_date,
                type,
                title,
                info,
                currency,
                amount,
                fees_taxes,
                net,
                tax_details,
                posted_at,
                journal_entry_id
            FROM etsy_transactions
            ORDER BY transaction_date DESC, id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "date": row["transaction_date"],
            "type": row["type"],
            "title": row["title"],
            "info": row["info"],
            "currency": row["currency"],
            "amount": row["amount"],
            "feesTaxes": row["fees_taxes"],
            "net": row["net"],
            "taxDetails": row["tax_details"],
            "posted": row["posted_at"] is not None,
            "journalEntryId": row["journal_entry_id"],
        }
        for row in rows
    ]


@app.get("/api/transactions/journal")
def get_journal_entries() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                je.id AS journal_entry_id,
                je.entry_date,
                je.source,
                je.memo AS entry_memo,
                je.status,
                jl.debit,
                jl.credit,
                jl.memo AS line_memo,
                a.code AS account_code,
                a.name AS account_name
            FROM journal_entries je
            JOIN journal_lines jl ON jl.journal_entry_id = je.id
            JOIN accounts a ON a.id = jl.account_id
            ORDER BY je.entry_date DESC, je.id DESC, jl.id
            """
        ).fetchall()

    grouped_entries: dict[int, dict[str, Any]] = {}

    for row in rows:
        entry_id = row["journal_entry_id"]
        entry = grouped_entries.setdefault(
            entry_id,
            {
                "id": entry_id,
                "date": row["entry_date"],
                "memo": row["entry_memo"],
                "source": row["source"],
                "debits": [],
                "credits": [],
                "amount": 0,
                "status": row["status"],
            },
        )

        line = {
            "accountCode": row["account_code"],
            "accountName": row["account_name"],
            "amount": row["debit"] or row["credit"],
            "memo": row["line_memo"],
        }

        if row["debit"]:
            entry["debits"].append(line)
            entry["amount"] = round(entry["amount"] + row["debit"], 2)

        if row["credit"]:
            entry["credits"].append(line)

    return list(grouped_entries.values())
