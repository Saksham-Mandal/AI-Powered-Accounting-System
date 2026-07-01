import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TextIO

try:
    from .models import EtsyTransaction, ImportSummary
except ImportError:
    from models import EtsyTransaction, ImportSummary


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
DATE_FORMAT = "%B %d, %Y"


def parse_money(value: str | None) -> float:
    if value is None:
        return 0.0

    cleaned = value.strip()
    if cleaned in {"", "--"}:
        return 0.0

    is_parenthesized = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.replace("$", "").replace(",", "").replace("(", "").replace(")", "")

    amount = float(cleaned)
    return -amount if is_parenthesized else amount


def parse_date(value: str) -> str:
    return datetime.strptime(value.strip(), DATE_FORMAT).date().isoformat()


def parse_csv(csvfile: str | Path) -> list[EtsyTransaction]:
    csv_path = Path(csvfile)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        return parse_csv_rows(file, csv_path.name)


def parse_csv_content(contents: bytes, filename: str) -> list[EtsyTransaction]:
    text = contents.decode("utf-8-sig")
    file = io.StringIO(text, newline="")
    return parse_csv_rows(file, filename)


def parse_csv_rows(file: TextIO, filename: str) -> list[EtsyTransaction]:
    transactions: list[EtsyTransaction] = []

    reader = csv.DictReader(file)

    for source_row, row in enumerate(reader, start=2):
        transactions.append(
            EtsyTransaction(
                source_file=filename,
                source_row=source_row,
                transaction_date=parse_date(row["Date"]),
                type=row["Type"].strip(),
                title=row["Title"].strip(),
                info=row["Info"].strip(),
                currency=row["Currency"].strip(),
                amount=parse_money(row["Amount"]),
                fees_taxes=parse_money(row["Fees & Taxes"]),
                net=parse_money(row["Net"]),
                tax_details=row["Tax Details"].strip(),
            )
        )

    return transactions


def import_etsy_csv(
    csvfile: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> ImportSummary:
    csv_path = Path(csvfile)
    contents = csv_path.read_bytes()
    return import_etsy_csv_content(contents, csv_path.name, db_path, period_id)


def import_etsy_csv_content(
    contents: bytes,
    filename: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> ImportSummary:
    transactions = parse_csv_content(contents, filename)
    file_hash = hashlib.sha256(contents).hexdigest()
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_file) as conn:
        ensure_import_tables(conn)

        imported = 0
        skipped = 0
        import_id = get_existing_import_id(conn, "etsy", file_hash)

        if import_id is not None:
            return ImportSummary(
                imported=0,
                skipped=len(transactions),
                total_rows=len(transactions),
            )

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
                "etsy",
                "etsy",
                filename,
                file_hash,
                len(transactions),
                "imported",
            ),
        )
        import_id = cursor.lastrowid

        for transaction in transactions:
            if transaction_exists(conn, import_id, transaction):
                skipped += 1
                continue

            staged_transaction_id = create_staged_transaction(
                conn,
                transaction,
                import_id,
                period_id,
            )

            cursor = conn.execute(
                """
                INSERT INTO etsy_transactions (
                    period_id,
                    import_id,
                    staged_transaction_id,
                    source_file,
                    source_row,
                    transaction_date,
                    type,
                    title,
                    info,
                    currency,
                    amount,
                    fees_taxes,
                    net,
                    tax_details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    period_id,
                    import_id,
                    staged_transaction_id,
                    transaction.source_file,
                    transaction.source_row,
                    transaction.transaction_date,
                    transaction.type,
                    transaction.title,
                    transaction.info,
                    transaction.currency,
                    transaction.amount,
                    transaction.fees_taxes,
                    transaction.net,
                    transaction.tax_details,
                ),
            )

            if staged_transaction_id is not None:
                conn.execute(
                    """
                    UPDATE staged_transactions
                    SET source_id = ?
                    WHERE id = ?
                    """,
                    (cursor.lastrowid, staged_transaction_id),
                )

            imported += 1

    return ImportSummary(
        imported=imported,
        skipped=skipped,
        total_rows=len(transactions),
    )


def ensure_import_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'etsy',
            filename TEXT NOT NULL,
            file_hash TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'imported',
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "imports", "period_id", "INTEGER")
    ensure_column(conn, "imports", "source_type", "TEXT NOT NULL DEFAULT 'etsy'")
    ensure_column(conn, "imports", "status", "TEXT NOT NULL DEFAULT 'imported'")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_imports_source_file_hash
        ON imports(source, file_hash)
        WHERE file_hash IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etsy_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            import_id INTEGER,
            staged_transaction_id INTEGER,
            source_file TEXT,
            source_row INTEGER NOT NULL,
            transaction_date TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            info TEXT,
            currency TEXT,
            amount REAL NOT NULL DEFAULT 0,
            fees_taxes REAL NOT NULL DEFAULT 0,
            net REAL NOT NULL DEFAULT 0,
            tax_details TEXT,
            review_status TEXT NOT NULL DEFAULT 'unreviewed',
            review_note TEXT,
            flagged_reason TEXT,
            proposed_journal_entry_id INTEGER,
            posted_at TEXT,
            journal_entry_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (import_id) REFERENCES imports(id)
        )
        """
    )
    ensure_column(conn, "etsy_transactions", "period_id", "INTEGER")
    ensure_column(conn, "etsy_transactions", "staged_transaction_id", "INTEGER")
    ensure_column(conn, "etsy_transactions", "proposed_journal_entry_id", "INTEGER")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_etsy_transactions_import_row
        ON etsy_transactions(import_id, source_row)
        WHERE import_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_etsy_transactions_source_file_row
        ON etsy_transactions(source_file, source_row)
        WHERE source_file IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_etsy_transactions_period
        ON etsy_transactions(period_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS staged_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            import_id INTEGER,
            source TEXT NOT NULL,
            source_table TEXT,
            source_id INTEGER,
            transaction_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            raw_payload TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_note TEXT,
            flagged_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (import_id) REFERENCES imports(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_staged_transactions_import
        ON staged_transactions(import_id)
        """
    )


def get_existing_import_id(
    conn: sqlite3.Connection,
    source: str,
    file_hash: str,
) -> int | None:
    cursor = conn.execute(
        """
        SELECT id
        FROM imports
        WHERE source = ?
          AND file_hash = ?
        LIMIT 1
        """,
        (
            source,
            file_hash,
        ),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def create_staged_transaction(
    conn: sqlite3.Connection,
    transaction: EtsyTransaction,
    import_id: int,
    period_id: int | None,
) -> int | None:
    if period_id is None:
        return None

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
            "etsy",
            "etsy_transactions",
            transaction.transaction_date,
            transaction.type,
            build_description(transaction),
            transaction.net,
            transaction.currency,
            json.dumps(
                {
                    "source_row": transaction.source_row,
                    "title": transaction.title,
                    "info": transaction.info,
                    "amount": transaction.amount,
                    "fees_taxes": transaction.fees_taxes,
                    "net": transaction.net,
                    "tax_details": transaction.tax_details,
                }
            ),
            "pending",
        ),
    )
    return cursor.lastrowid


def build_description(transaction: EtsyTransaction) -> str:
    parts = [transaction.type, transaction.title, transaction.info]
    return " - ".join(part.strip() for part in parts if part.strip())


def ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def transaction_exists(
    conn: sqlite3.Connection,
    import_id: int,
    transaction: EtsyTransaction,
) -> bool:
    cursor = conn.execute(
        """
        SELECT 1
        FROM etsy_transactions
        WHERE import_id = ?
          AND source_row = ?
        LIMIT 1
        """,
        (
            import_id,
            transaction.source_row,
        ),
    )
    return cursor.fetchone() is not None


if __name__ == "__main__":
    csv_path = BASE_DIR / "etsy_statement_2026_1.csv"
    summary = import_etsy_csv(csv_path)
    print(
        f"Imported {summary.imported} rows, skipped {summary.skipped} duplicates "
        f"out of {summary.total_rows} total rows."
    )
