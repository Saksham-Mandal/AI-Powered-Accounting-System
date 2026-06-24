import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "accounting.db"

ACCOUNTS = [
    ("1000", "Cash", "asset", "debit"),
    ("1010", "Etsy Clearing", "asset", "debit"),
    ("1100", "Accounts Receivable", "asset", "debit"),
    ("1200", "Inventory", "asset", "debit"),
    ("1300", "Supplies", "asset", "debit"),
    ("2000", "Accounts Payable", "liability", "credit"),
    ("2100", "Sales Tax Payable", "liability", "credit"),
    ("3000", "Owner Capital", "equity", "credit"),
    ("3100", "Owner Contributions", "equity", "credit"),
    ("3200", "Owner Draws", "equity", "debit"),
    ("4000", "Sales Revenue", "revenue", "credit"),
    ("4050", "Sales Returns and Allowances", "contra_revenue", "debit"),
    ("4100", "Shipping Revenue", "revenue", "credit"),
    ("5000", "Cost of Goods Sold", "expense", "debit"),
    ("5100", "Etsy Fees Expense", "expense", "debit"),
    ("5200", "Shipping Expense", "expense", "debit"),
    ("5300", "Materials Expense", "expense", "debit"),
    ("5400", "Marketing Expense", "expense", "debit"),
    ("5500", "Software Expense", "expense", "debit"),
    ("5900", "Uncategorized Expense", "expense", "debit"),
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


if __name__ == "__main__":
    account_count = seed_accounts()
    print(f"Seeded {account_count} accounts.")
