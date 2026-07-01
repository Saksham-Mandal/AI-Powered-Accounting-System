import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TextIO

try:
    from .csv_parser import ensure_import_tables, get_existing_import_id
    from .models import GeneratedTransactionRow, ImportSummary, JournalLine
    from .post_transacs import (
        ensure_proposed_journal_tables,
        get_account_ids,
        validate_balanced,
        validate_required_accounts,
    )
except ImportError:
    from csv_parser import ensure_import_tables, get_existing_import_id
    from models import GeneratedTransactionRow, ImportSummary, JournalLine
    from post_transacs import (
        ensure_proposed_journal_tables,
        get_account_ids,
        validate_balanced,
        validate_required_accounts,
    )


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
REQUIRED_COLUMNS = {
    "entry_date",
    "memo",
    "debit_account",
    "credit_account",
    "debit_amount",
    "credit_amount",
    "source",
    "source_id",
}


def parse_transaction_csv(csvfile: str | Path) -> list[GeneratedTransactionRow]:
    csv_path = Path(csvfile)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        return parse_transaction_csv_rows(file)


def parse_transaction_csv_content(contents: bytes) -> list[GeneratedTransactionRow]:
    text = contents.decode("utf-8-sig")
    file = io.StringIO(text, newline="")
    return parse_transaction_csv_rows(file)


def parse_transaction_csv_rows(file: TextIO) -> list[GeneratedTransactionRow]:
    reader = csv.DictReader(file)
    missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Transaction CSV is missing columns: {missing}")

    rows: list[GeneratedTransactionRow] = []
    for source_row, row in enumerate(reader, start=2):
        rows.append(parse_transaction_row(row, source_row))

    return rows


def parse_transaction_row(
    row: dict[str, str],
    source_row: int,
) -> GeneratedTransactionRow:
    entry_date = parse_entry_date(row["entry_date"], source_row)
    debit_amount = parse_positive_amount(row["debit_amount"], source_row, "debit_amount")
    credit_amount = parse_positive_amount(
        row["credit_amount"],
        source_row,
        "credit_amount",
    )

    if debit_amount != credit_amount:
        raise ValueError(
            f"Row {source_row} is not balanced: debit_amount must equal credit_amount."
        )

    memo = row["memo"].strip()
    debit_account = row["debit_account"].strip()
    credit_account = row["credit_account"].strip()
    source = row["source"].strip()
    source_id = row["source_id"].strip()

    if not memo:
        raise ValueError(f"Row {source_row} is missing a memo.")

    if not debit_account or not credit_account:
        raise ValueError(f"Row {source_row} is missing an account code.")

    if not source:
        raise ValueError(f"Row {source_row} is missing a source.")

    return GeneratedTransactionRow(
        entry_date=entry_date,
        memo=memo,
        debit_account=debit_account,
        credit_account=credit_account,
        debit_amount=debit_amount,
        credit_amount=credit_amount,
        source=source,
        source_id=source_id,
    )


def import_transaction_csv(
    csvfile: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> ImportSummary:
    csv_path = Path(csvfile)
    contents = csv_path.read_bytes()
    return import_transaction_csv_content(contents, csv_path.name, db_path, period_id)


def import_transaction_csv_content(
    contents: bytes,
    filename: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> ImportSummary:
    if period_id is None:
        raise ValueError("A period_id is required to import transaction CSV rows.")

    transactions = parse_transaction_csv_content(contents)
    file_hash = hashlib.sha256(contents).hexdigest()
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_import_tables(conn)
        ensure_proposed_journal_tables(conn)
        account_ids = get_account_ids(conn)

        existing_import_id = get_existing_import_id(conn, "transaction_csv", file_hash)
        if existing_import_id is not None:
            return ImportSummary(
                imported=0,
                skipped=len(transactions),
                total_rows=len(transactions),
            )

        import_id = create_transaction_import(
            conn,
            filename,
            file_hash,
            len(transactions),
            period_id,
        )

        imported = 0
        skipped = 0

        for source_row, transaction in enumerate(transactions, start=2):
            lines = build_transaction_journal_lines(transaction)
            validate_required_accounts(lines, account_ids)
            validate_balanced(lines)

            staged_transaction_id = create_transaction_staging_row(
                conn,
                transaction,
                source_row,
                import_id,
                period_id,
            )
            create_transaction_proposal(
                conn,
                transaction,
                lines,
                account_ids,
                import_id,
                period_id,
                staged_transaction_id,
            )
            imported += 1

    return ImportSummary(
        imported=imported,
        skipped=skipped,
        total_rows=len(transactions),
    )


def build_transaction_journal_lines(
    transaction: GeneratedTransactionRow,
) -> list[JournalLine]:
    return [
        JournalLine(
            account_code=transaction.debit_account,
            debit=transaction.debit_amount,
            memo=transaction.memo,
        ),
        JournalLine(
            account_code=transaction.credit_account,
            credit=transaction.credit_amount,
            memo=transaction.memo,
        ),
    ]


def create_transaction_import(
    conn: sqlite3.Connection,
    filename: str,
    file_hash: str,
    row_count: int,
    period_id: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO imports (
            period_id,
            source,
            source_type,
            filename,
            file_hash,
            row_count,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            period_id,
            "transaction_csv",
            "transaction_csv",
            filename,
            file_hash,
            row_count,
            "imported",
        ),
    )
    return cursor.lastrowid


def create_transaction_staging_row(
    conn: sqlite3.Connection,
    transaction: GeneratedTransactionRow,
    source_row: int,
    import_id: int,
    period_id: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO staged_transactions (
            period_id,
            import_id,
            source,
            source_table,
            transaction_date,
            transaction_type,
            description,
            amount,
            currency,
            raw_payload,
            review_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            period_id,
            import_id,
            transaction.source,
            "transaction_csv",
            transaction.entry_date,
            "Journal Entry",
            transaction.memo,
            transaction.debit_amount,
            "USD",
            json.dumps(
                {
                    "source_row": source_row,
                    "source": transaction.source,
                    "source_id": transaction.source_id,
                    "debit_account": transaction.debit_account,
                    "credit_account": transaction.credit_account,
                    "debit_amount": transaction.debit_amount,
                    "credit_amount": transaction.credit_amount,
                }
            ),
            "pending",
        ),
    )
    return cursor.lastrowid


def create_transaction_proposal(
    conn: sqlite3.Connection,
    transaction: GeneratedTransactionRow,
    lines: list[JournalLine],
    account_ids: dict[str, int],
    import_id: int,
    period_id: int,
    staged_transaction_id: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO proposed_journal_entries (
            period_id,
            import_id,
            staged_transaction_id,
            entry_date,
            entry_type,
            source,
            source_table,
            source_id,
            memo,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            period_id,
            import_id,
            staged_transaction_id,
            transaction.entry_date,
            "regular",
            transaction.source,
            "staged_transactions",
            staged_transaction_id,
            transaction.memo,
            "pending",
        ),
    )
    proposed_journal_entry_id = cursor.lastrowid

    for line in lines:
        conn.execute(
            """
            INSERT INTO proposed_journal_lines (
                proposed_journal_entry_id,
                account_id,
                debit,
                credit,
                memo
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                proposed_journal_entry_id,
                account_ids[line.account_code],
                line.debit,
                line.credit,
                line.memo,
            ),
        )

    return proposed_journal_entry_id


def parse_entry_date(value: str, source_row: int) -> str:
    cleaned = value.strip()

    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError(
            f"Row {source_row} has an invalid entry_date. Use YYYY-MM-DD."
        ) from error


def parse_positive_amount(value: str, source_row: int, column_name: str) -> float:
    try:
        amount = round(float(value.strip()), 2)
    except ValueError as error:
        raise ValueError(f"Row {source_row} has an invalid {column_name}.") from error

    if amount <= 0:
        raise ValueError(f"Row {source_row} {column_name} must be greater than zero.")

    return amount


if __name__ == "__main__":
    csv_path = BASE_DIR / "csv_files" / "generated_variable_cost_transactions.csv"
    summary = import_transaction_csv(csv_path, period_id=1)
    print(
        f"Imported {summary.imported} rows, skipped {summary.skipped} duplicates "
        f"out of {summary.total_rows} total rows."
    )
