import csv
import sqlite3
from datetime import datetime
from pathlib import Path

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
    transactions: list[EtsyTransaction] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for source_row, row in enumerate(reader, start=2):
            transactions.append(
                EtsyTransaction(
                    source_file=csv_path.name,
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
) -> ImportSummary:
    transactions = parse_csv(csvfile)
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_file) as conn:
        ensure_etsy_table(conn)

        imported = 0
        skipped = 0

        for transaction in transactions:
            if transaction_exists(conn, transaction):
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO etsy_transactions (
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
            imported += 1

    return ImportSummary(
        imported=imported,
        skipped=skipped,
        total_rows=len(transactions),
    )


def ensure_etsy_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etsy_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            source_row INTEGER,
            transaction_date TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            info TEXT,
            currency TEXT,
            amount REAL DEFAULT 0,
            fees_taxes REAL DEFAULT 0,
            net REAL DEFAULT 0,
            tax_details TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "etsy_transactions", "source_file", "TEXT")
    ensure_column(conn, "etsy_transactions", "source_row", "INTEGER")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_etsy_transactions_source_row
        ON etsy_transactions(source_file, source_row)
        """
    )


def transaction_exists(conn: sqlite3.Connection, transaction: EtsyTransaction) -> bool:
    cursor = conn.execute(
        """
        SELECT 1
        FROM etsy_transactions
        WHERE source_file = ?
          AND source_row = ?
        LIMIT 1
        """,
        (
            transaction.source_file,
            transaction.source_row,
        ),
    )
    return cursor.fetchone() is not None


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


if __name__ == "__main__":
    csv_path = BASE_DIR / "etsy_statement_2026_1.csv"
    summary = import_etsy_csv(csv_path)
    print(
        f"Imported {summary.imported} rows, skipped {summary.skipped} duplicates "
        f"out of {summary.total_rows} total rows."
    )
