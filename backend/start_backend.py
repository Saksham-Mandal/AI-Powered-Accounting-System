import sqlite3
from pathlib import Path

import uvicorn
from csv_parser import import_etsy_csv
from db.account_chart import seed_accounts
from db.cleardb import clear_accounts, clear_csv_and_transactions
from db.initdb import initdb
from post_transacs import post_approved_proposals, propose_etsy_transactions


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "accounting.db"
DEFAULT_CSV_PATH = BASE_DIR / "etsy_statement_2026_1.csv"
CURRENT_PERIOD = {
    "period_start": "2026-01-01",
    "period_end": "2026-01-31",
    "label": "January 2026",
}


def main() -> None:
    while True:
        command = input(
            """
What do you want to do?
[init (i)]: Initialize the database schema
[accounts (a)]: Seed the chart of accounts
[reset (r)]: Rebuild the database and seed accounts
[clear-data (cd)]: Clear imports, CSV rows, periods, and journal entries
[clear-accounts (ca)]: Clear the accounts table
[import-sample (is)]: Import the sample Etsy CSV and create proposed entries
[propose (p)]: Create proposed entries from unproposed Etsy rows
[post-ledger (pl)]: Post proposed entries to the ledger
[start (s)]: Start the backend server
[quit (q)]: Quit
> """
        ).lower().strip()

        if command in {"init", "i"}:
            initialize_database()
        elif command in {"accounts", "a"}:
            seed_chart_of_accounts()
        elif command in {"reset", "r"}:
            reset_database()
        elif command in {"clear-data", "cd"}:
            clear_imported_data()
        elif command in {"clear-accounts", "ca"}:
            clear_chart_of_accounts()
        elif command in {"import-sample", "is"}:
            import_sample_csv()
        elif command in {"propose", "p"}:
            propose_unproposed_etsy_rows()
        elif command in {"post-ledger", "pl"}:
            post_proposals_to_ledger()
        elif command in {"start", "s"}:
            start_backend()
            break
        elif command in {"quit", "q"}:
            print("Goodbye.")
            break
        else:
            print("Invalid command. Please choose one of the listed options.")


def initialize_database() -> None:
    print("Initializing database schema...")
    initdb()
    print("Database schema initialized.")


def seed_chart_of_accounts() -> None:
    print("Seeding chart of accounts...")
    account_count = seed_accounts()
    print(f"Seeded {account_count} accounts.")


def reset_database() -> None:
    print("Rebuilding database...")
    initdb()
    account_count = seed_accounts()
    print(f"Database rebuilt and {account_count} accounts seeded.")


def clear_imported_data() -> None:
    print("Clearing imported CSV and transaction data...")
    deleted_counts = clear_csv_and_transactions()
    print_deleted_counts(deleted_counts)
    print("Imported data cleared.")


def clear_chart_of_accounts() -> None:
    print("Clearing accounts...")
    deleted_counts = clear_accounts()
    print_deleted_counts(deleted_counts)
    print("Accounts cleared.")


def import_sample_csv() -> None:
    if not DEFAULT_CSV_PATH.exists():
        print(f"Sample CSV not found: {DEFAULT_CSV_PATH}")
        return

    period_id = ensure_current_period()

    print(f"Importing sample CSV: {DEFAULT_CSV_PATH.name}")
    import_summary = import_etsy_csv(DEFAULT_CSV_PATH, period_id=period_id)
    print(
        f"Imported {import_summary.imported} rows, skipped "
        f"{import_summary.skipped} duplicates out of "
        f"{import_summary.total_rows} total rows."
    )

    propose_unproposed_etsy_rows()


def propose_unproposed_etsy_rows() -> None:
    print("Creating proposed journal entries from unproposed Etsy rows...")
    proposal_summary = propose_etsy_transactions()
    print(
        f"Created {proposal_summary.proposed} proposed journal entries, skipped "
        f"{proposal_summary.skipped} rows out of "
        f"{proposal_summary.total_unproposed} unproposed Etsy rows."
    )


def post_proposals_to_ledger() -> None:
    period_id = ensure_current_period()
    print("Posting proposed journal entries to the ledger...")
    posting_summary = post_approved_proposals(period_id)
    print(
        f"Posted {posting_summary.posted} proposed entries, skipped "
        f"{posting_summary.skipped} entries out of "
        f"{posting_summary.total_proposals} available proposals."
    )


def ensure_current_period() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO accounting_periods (
                period_start,
                period_end,
                label,
                status
            )
            VALUES (?, ?, ?, 'open')
            ON CONFLICT(period_start, period_end) DO NOTHING
            """,
            (
                CURRENT_PERIOD["period_start"],
                CURRENT_PERIOD["period_end"],
                CURRENT_PERIOD["label"],
            ),
        )
        row = conn.execute(
            """
            SELECT id
            FROM accounting_periods
            WHERE period_start = ?
              AND period_end = ?
            LIMIT 1
            """,
            (
                CURRENT_PERIOD["period_start"],
                CURRENT_PERIOD["period_end"],
            ),
        ).fetchone()

    if row is None:
        raise RuntimeError("Current accounting period could not be created.")

    return int(row[0])


def start_backend() -> None:
    print("Starting backend server at http://127.0.0.1:8000")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)


def print_deleted_counts(deleted_counts: dict[str, int]) -> None:
    for table, count in deleted_counts.items():
        print(f"- {table}: {count} rows")


if __name__ == "__main__":
    main()
