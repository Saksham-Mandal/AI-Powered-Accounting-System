import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "accounting.db"

ACCOUNTS = [
    ("1000", "Cash", "asset", "debit"),
    ("1010", "Etsy Clearing", "asset", "debit"),
    ("1100", "Accounts Receivable", "asset", "debit"),
    ("1200", "Materials", "asset", "debit"),
    ("1300", "Supplies", "asset", "debit"),
    ("2000", "Accounts Payable", "liability", "credit"),
    ("3000", "Capital", "equity", "credit"),
    ("3900", "Income Summary", "equity", "credit"),
    ("4000", "Sales Revenue", "revenue", "credit"),
    ("4050", "Sales Returns and Allowances", "contra_revenue", "debit"),
    ("5100", "Etsy Fees Expense", "expense", "debit"),
    ("5150", "Sales Tax Expense", "expense", "debit"),
    ("5200", "Shipping Expense", "expense", "debit"),
    ("5300", "Materials Expense", "expense", "debit"),
    ("5400", "Supplies Expense", "expense", "debit"),
    ("5500", "Marketing Expense", "expense", "debit"),
    ("5600", "Software Expense", "expense", "debit"),
    ("5900", "Uncategorized Expense", "expense", "debit"),
]
REMOVED_ACCOUNT_CODES = [
    "2100",
    "3100",
    "3200",
    "4100",
    "5000",
]


def seed_accounts(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        ensure_accounts_table(conn)
        conn.executemany(
            """
            INSERT INTO accounts (
                code,
                name,
                account_type,
                normal_balance
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                account_type = excluded.account_type,
                normal_balance = excluded.normal_balance,
                is_active = 1
            """,
            ACCOUNTS,
        )
        deactivate_removed_accounts(conn)

    return len(ACCOUNTS)


def ensure_accounts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            normal_balance TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def deactivate_removed_accounts(conn: sqlite3.Connection) -> None:
    placeholders = ", ".join("?" for _ in REMOVED_ACCOUNT_CODES)
    conn.execute(
        f"""
        UPDATE accounts
        SET is_active = 0
        WHERE code IN ({placeholders})
        """,
        REMOVED_ACCOUNT_CODES,
    )


if __name__ == "__main__":
    account_count = seed_accounts()
    print(f"Seeded {account_count} accounts.")
