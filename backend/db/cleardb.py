import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "accounting.db"

TRANSACTION_TABLES = [
    "income_statement_snapshots",
    "proposed_journal_lines",
    "journal_lines",
    "etsy_transactions",
    "manual_expenses",
    "proposed_journal_entries",
    "journal_entries",
    "closing_batches",
    "staged_transactions",
    "imports",
    "accounting_periods",
]


def clear_csv_and_transactions(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """
    Clear imported CSV rows, journal entries, periods, and manual transaction data.

    This keeps the chart of accounts intact so you can test the import/posting
    process again without reseeding accounts.
    """
    return _clear_tables(TRANSACTION_TABLES, db_path)


def clear_accounts(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """
    Clear the accounts table.

    Run clear_csv_and_transactions first if the database contains journal lines,
    because journal_lines.account_id points at accounts.id.
    """
    return _clear_tables(["accounts"], db_path)


def _clear_tables(
    tables: list[str],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    db_file = Path(db_path)
    deleted_counts: dict[str, int] = {}

    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")

        for table in tables:
            if not _table_exists(conn, table):
                deleted_counts[table] = 0
                continue

            deleted_counts[table] = _count_rows(conn, table)
            conn.execute(f"DELETE FROM {table}")

        _reset_autoincrement(conn, tables)

    return deleted_counts


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table,),
    ).fetchone()
    return row is not None


def _reset_autoincrement(conn: sqlite3.Connection, tables: list[str]) -> None:
    existing_tables = [table for table in tables if _table_exists(conn, table)]

    if not existing_tables:
        return

    placeholders = ", ".join("?" for _ in existing_tables)
    conn.execute(
        f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
        existing_tables,
    )


if __name__ == "__main__":
    deleted = clear_csv_and_transactions()

    print("Cleared CSV and transaction data:")
    for table, count in deleted.items():
        print(f"- {table}: {count} rows")
