import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "accounting.db"

TRANSACTION_TABLES = [
    "balance_sheet_snapshot_lines",
    "balance_sheet_snapshots",
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


def rollback_period(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int | str | None]:
    """
    Delete one accounting period and every imported, proposed, posted, and
    statement-snapshot record tied to it.
    """
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = OFF")

        period = conn.execute(
            """
            SELECT id, label
            FROM accounting_periods
            WHERE id = ?
            """,
            (period_id,),
        ).fetchone()

        if period is None:
            raise ValueError(f"Accounting period {period_id} does not exist.")

        counts: dict[str, int | str | None] = {
            "period_id": period["id"],
            "period_label": period["label"],
        }

        journal_entry_ids = _ids_for_period(conn, "journal_entries", period_id)
        proposed_entry_ids = _ids_for_period(conn, "proposed_journal_entries", period_id)
        snapshot_ids = _ids_for_period(conn, "balance_sheet_snapshots", period_id)
        staged_transaction_ids = _ids_for_period(conn, "staged_transactions", period_id)
        import_ids = _ids_for_period(conn, "imports", period_id)
        closing_batch_ids = _ids_for_period(conn, "closing_batches", period_id)

        counts["balance_sheet_snapshot_lines"] = _delete_by_parent_ids(
            conn,
            "balance_sheet_snapshot_lines",
            "snapshot_id",
            snapshot_ids,
        )
        counts["balance_sheet_snapshots"] = _delete_by_ids(
            conn,
            "balance_sheet_snapshots",
            snapshot_ids,
        )
        counts["income_statement_snapshots"] = _delete_for_period(
            conn,
            "income_statement_snapshots",
            period_id,
        )
        counts["journal_lines"] = _delete_by_parent_ids(
            conn,
            "journal_lines",
            "journal_entry_id",
            journal_entry_ids,
        )
        counts["proposed_journal_lines"] = _delete_by_parent_ids(
            conn,
            "proposed_journal_lines",
            "proposed_journal_entry_id",
            proposed_entry_ids,
        )
        counts["etsy_transactions"] = _delete_for_period(
            conn,
            "etsy_transactions",
            period_id,
        )
        counts["manual_expenses"] = _delete_for_period(
            conn,
            "manual_expenses",
            period_id,
        )
        counts["proposed_journal_entries"] = _delete_by_ids(
            conn,
            "proposed_journal_entries",
            proposed_entry_ids,
        )
        counts["journal_entries"] = _delete_by_ids(
            conn,
            "journal_entries",
            journal_entry_ids,
        )
        counts["closing_batches"] = _delete_by_ids(
            conn,
            "closing_batches",
            closing_batch_ids,
        )
        counts["staged_transactions"] = _delete_by_ids(
            conn,
            "staged_transactions",
            staged_transaction_ids,
        )
        counts["imports"] = _delete_by_ids(conn, "imports", import_ids)
        counts["accounting_periods"] = _delete_for_period(
            conn,
            "accounting_periods",
            period_id,
            period_column="id",
        )

        _reset_autoincrement(conn, TRANSACTION_TABLES)

    return counts


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


def _ids_for_period(
    conn: sqlite3.Connection,
    table: str,
    period_id: int,
) -> list[int]:
    if not _table_exists(conn, table):
        return []

    rows = conn.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE period_id = ?
        """,
        (period_id,),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _delete_for_period(
    conn: sqlite3.Connection,
    table: str,
    period_id: int,
    period_column: str = "period_id",
) -> int:
    if not _table_exists(conn, table):
        return 0

    return conn.execute(
        f"""
        DELETE FROM {table}
        WHERE {period_column} = ?
        """,
        (period_id,),
    ).rowcount


def _delete_by_ids(
    conn: sqlite3.Connection,
    table: str,
    row_ids: list[int],
) -> int:
    if not row_ids or not _table_exists(conn, table):
        return 0

    placeholders = ", ".join("?" for _ in row_ids)
    return conn.execute(
        f"""
        DELETE FROM {table}
        WHERE id IN ({placeholders})
        """,
        row_ids,
    ).rowcount


def _delete_by_parent_ids(
    conn: sqlite3.Connection,
    table: str,
    parent_column: str,
    parent_ids: list[int],
) -> int:
    if not parent_ids or not _table_exists(conn, table):
        return 0

    placeholders = ", ".join("?" for _ in parent_ids)
    return conn.execute(
        f"""
        DELETE FROM {table}
        WHERE {parent_column} IN ({placeholders})
        """,
        parent_ids,
    ).rowcount


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
