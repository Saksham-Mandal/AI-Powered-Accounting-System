import sqlite3
from pathlib import Path

try:
    from .models import JournalLine, PostingSummary
except ImportError:
    from models import JournalLine, PostingSummary


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
ETSY_CLEARING = "1010"


def post_etsy_transactions(db_path: str | Path = DEFAULT_DB_PATH) -> PostingSummary:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_journal_tables(conn)
        ensure_posting_columns(conn)
        account_ids = get_account_ids(conn)
        transactions = get_unposted_etsy_transactions(conn)

        posted = 0
        skipped = 0

        for transaction in transactions:
            lines = build_journal_lines(transaction)

            if not lines:
                mark_transaction_posted(conn, transaction["id"], None)
                skipped += 1
                continue

            validate_required_accounts(lines, account_ids)
            validate_balanced(lines)
            journal_entry_id = create_journal_entry(conn, transaction, lines, account_ids)
            mark_transaction_posted(conn, transaction["id"], journal_entry_id)
            posted += 1

    return PostingSummary(
        posted=posted,
        skipped=skipped,
        total_unposted=len(transactions),
    )


def get_unposted_etsy_transactions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM etsy_transactions
        WHERE posted_at IS NULL
        ORDER BY transaction_date, id
        """
    ).fetchall()


def ensure_journal_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            source TEXT NOT NULL,
            source_table TEXT,
            source_id INTEGER,
            memo TEXT,
            status TEXT NOT NULL DEFAULT 'posted',
            posted_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_entries_source_record
        ON journal_entries(source, source_table, source_id)
        WHERE source_table IS NOT NULL
          AND source_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_journal_entries_date
        ON journal_entries(entry_date);

        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_entry_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit REAL NOT NULL DEFAULT 0,
            credit REAL NOT NULL DEFAULT 0,
            memo TEXT,
            FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE INDEX IF NOT EXISTS idx_journal_lines_entry
        ON journal_lines(journal_entry_id);

        CREATE INDEX IF NOT EXISTS idx_journal_lines_account
        ON journal_lines(account_id);
        """
    )


def ensure_posting_columns(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "etsy_transactions", "posted_at", "TEXT")
    ensure_column(conn, "etsy_transactions", "journal_entry_id", "INTEGER")


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


def build_journal_lines(transaction: sqlite3.Row) -> list[JournalLine]:
    transaction_type = transaction["type"]
    net = round(float(transaction["net"] or 0), 2)
    amount = abs(net)
    memo = build_memo(transaction)

    if amount == 0:
        return []

    if transaction_type == "Sale":
        return build_sale_lines(net, amount, memo)

    if transaction_type == "Refund":
        return build_refund_lines(net, amount, memo)

    if transaction_type == "Fee":
        return build_expense_or_credit_lines("5100", net, amount, memo)

    if transaction_type == "Shipping":
        return build_expense_or_credit_lines("5200", net, amount, memo)

    if transaction_type == "Tax":
        return build_tax_lines(net, amount, memo)

    return build_expense_or_credit_lines("5900", net, amount, memo)


def build_sale_lines(net: float, amount: float, memo: str) -> list[JournalLine]:
    if net > 0:
        return [
            JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
            JournalLine("4000", credit=amount, memo=memo),
        ]

    return [
        JournalLine("4050", debit=amount, memo=memo),
        JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
    ]


def build_refund_lines(net: float, amount: float, memo: str) -> list[JournalLine]:
    if net < 0:
        return [
            JournalLine("4050", debit=amount, memo=memo),
            JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
        ]

    return [
        JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
        JournalLine("4050", credit=amount, memo=memo),
    ]


def build_expense_or_credit_lines(
    expense_account_code: str,
    net: float,
    amount: float,
    memo: str,
) -> list[JournalLine]:
    if net < 0:
        return [
            JournalLine(expense_account_code, debit=amount, memo=memo),
            JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
        ]

    return [
        JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
        JournalLine(expense_account_code, credit=amount, memo=memo),
    ]


def build_tax_lines(net: float, amount: float, memo: str) -> list[JournalLine]:
    if net < 0:
        return [
            JournalLine("2100", debit=amount, memo=memo),
            JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
        ]

    return [
        JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
        JournalLine("2100", credit=amount, memo=memo),
    ]


def create_journal_entry(
    conn: sqlite3.Connection,
    transaction: sqlite3.Row,
    lines: list[JournalLine],
    account_ids: dict[str, int],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO journal_entries (
            entry_date,
            source,
            source_table,
            source_id,
            memo,
            status,
            posted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            transaction["transaction_date"],
            "etsy",
            "etsy_transactions",
            transaction["id"],
            build_memo(transaction),
            "posted",
        ),
    )
    journal_entry_id = cursor.lastrowid

    for line in lines:
        conn.execute(
            """
            INSERT INTO journal_lines (
                journal_entry_id,
                account_id,
                debit,
                credit,
                memo
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                journal_entry_id,
                account_ids[line.account_code],
                line.debit,
                line.credit,
                line.memo,
            ),
        )

    return journal_entry_id


def mark_transaction_posted(
    conn: sqlite3.Connection,
    transaction_id: int,
    journal_entry_id: int | None,
) -> None:
    conn.execute(
        """
        UPDATE etsy_transactions
        SET posted_at = CURRENT_TIMESTAMP,
            journal_entry_id = ?
        WHERE id = ?
        """,
        (journal_entry_id, transaction_id),
    )


def get_account_ids(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        row["code"]: row["id"]
        for row in conn.execute(
            """
            SELECT id, code
            FROM accounts
            WHERE is_active = 1
            """
        ).fetchall()
    }


def validate_required_accounts(
    lines: list[JournalLine],
    account_ids: dict[str, int],
) -> None:
    missing_codes = sorted(
        {line.account_code for line in lines if line.account_code not in account_ids}
    )

    if missing_codes:
        missing = ", ".join(missing_codes)
        raise ValueError(f"Missing account codes in accounts table: {missing}")


def validate_balanced(lines: list[JournalLine]) -> None:
    total_debits = round(sum(line.debit for line in lines), 2)
    total_credits = round(sum(line.credit for line in lines), 2)

    if total_debits != total_credits:
        raise ValueError(
            f"Journal entry is not balanced: debits={total_debits}, "
            f"credits={total_credits}"
        )


def build_memo(transaction: sqlite3.Row) -> str:
    details = [transaction["type"], transaction["title"], transaction["info"]]
    return " - ".join(str(detail).strip() for detail in details if detail)


if __name__ == "__main__":
    summary = post_etsy_transactions()
    print(
        f"Posted {summary.posted} journal entries, skipped {summary.skipped} "
        f"zero-dollar rows out of {summary.total_unposted} unposted Etsy rows."
    )
