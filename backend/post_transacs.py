import re
import sqlite3
from pathlib import Path

try:
    from .models import JournalLine, LedgerPostSummary, PostingSummary, ProposalSummary
except ImportError:
    from models import JournalLine, LedgerPostSummary, PostingSummary, ProposalSummary


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
CASH = "1000"
ETSY_CLEARING = "1010"
SALES_TAX_EXPENSE = "5150"
MARKETING_EXPENSE = "5500"
MATERIALS_EXPENSE = "5300"
SUPPLIES_EXPENSE = "5400"
UNCATEGORIZED_EXPENSE = "5900"
UNCATEGORIZED_REVIEW_REASON = (
    "Journal entry uses Uncategorized Expense and should be reviewed."
)
KNOWN_TRANSACTION_TYPES = {
    "Deposit",
    "Fee",
    "Payment",
    "Refund",
    "Sale",
    "Shipping",
    "Materials Expense",
    "Marketing",
    "Supplies Expense",
    "Tax",
    "VAT",
}


def propose_etsy_transactions(
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> ProposalSummary:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_proposed_journal_tables(conn)
        ensure_posting_columns(conn)
        account_ids = get_account_ids(conn)
        transactions = get_unproposed_etsy_transactions(conn, period_id)

        proposed = 0
        skipped = 0

        for transaction in transactions:
            lines = build_journal_lines(transaction)
            flag_reason = get_review_flag(transaction, lines)

            if not lines:
                if flag_reason:
                    flag_transaction_for_review(conn, transaction["id"], flag_reason)
                skipped += 1
                continue

            validate_required_accounts(lines, account_ids)
            validate_balanced(lines)
            proposed_journal_entry_id = create_proposed_journal_entry(
                conn,
                transaction,
                lines,
                account_ids,
                flag_reason,
            )
            mark_transaction_proposed(
                conn,
                transaction["id"],
                proposed_journal_entry_id,
                flag_reason,
            )
            proposed += 1

    return ProposalSummary(
        proposed=proposed,
        skipped=skipped,
        total_unproposed=len(transactions),
    )


def post_approved_proposals(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> LedgerPostSummary:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_journal_tables(conn)
        ensure_proposed_journal_tables(conn)
        proposals = get_postable_proposals(conn, period_id)

        posted = 0
        skipped = 0

        for proposal in proposals:
            lines = get_proposed_journal_lines(conn, proposal["id"])

            if not lines:
                skipped += 1
                continue

            validate_balanced_rows(lines)
            journal_entry_id = create_journal_entry_from_proposal(conn, proposal, lines)
            mark_proposal_posted(conn, proposal["id"], journal_entry_id)
            mark_source_transaction_posted(conn, proposal, journal_entry_id)
            posted += 1

    return LedgerPostSummary(
        posted=posted,
        skipped=skipped,
        total_proposals=len(proposals),
    )


def create_manual_proposed_entry(
    period_id: int,
    entry_date: str,
    memo: str,
    lines: list[JournalLine],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_proposed_journal_tables(conn)
        account_ids = get_account_ids(conn)
        validate_required_accounts(lines, account_ids)
        validate_balanced(lines)
        flag_reason = get_line_review_flag(lines)

        cursor = conn.execute(
            """
            INSERT INTO proposed_journal_entries (
                period_id,
                entry_date,
                entry_type,
                source,
                memo,
                status,
                flagged_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                period_id,
                entry_date,
                "manual",
                "manual",
                memo,
                "needs_review" if flag_reason else "pending",
                flag_reason or None,
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
                    line.memo or memo,
                ),
            )

    return proposed_journal_entry_id


def flag_uncategorized_proposals(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[int]:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_proposed_journal_tables(conn)
        proposal_ids = get_uncategorized_proposal_ids(conn)

        if proposal_ids:
            placeholders = ", ".join("?" for _ in proposal_ids)
            conn.execute(
                f"""
                UPDATE proposed_journal_entries
                SET status = 'needs_review',
                    flagged_reason = COALESCE(flagged_reason, ?)
                WHERE id IN ({placeholders})
                  AND posted_journal_entry_id IS NULL
                  AND voided_at IS NULL
                """,
                (UNCATEGORIZED_REVIEW_REASON, *proposal_ids),
            )
            mark_linked_etsy_transactions_flagged(conn, proposal_ids)

    return proposal_ids


def void_proposed_entry(
    proposed_journal_entry_id: int,
    reason: str,
    note: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> bool:
    db_file = Path(db_path)
    review_note = " - ".join(part for part in [reason, note] if part)

    with sqlite3.connect(db_file) as conn:
        ensure_proposed_journal_tables(conn)
        cursor = conn.execute(
            """
            UPDATE proposed_journal_entries
            SET status = 'voided',
                voided_at = CURRENT_TIMESTAMP,
                review_note = ?
            WHERE id = ?
              AND posted_journal_entry_id IS NULL
              AND voided_at IS NULL
            """,
            (
                review_note or None,
                proposed_journal_entry_id,
            ),
        )

    return cursor.rowcount > 0


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
                flag_reason = get_review_flag(transaction, lines)
                if flag_reason:
                    flag_transaction_for_review(conn, transaction["id"], flag_reason)
                skipped += 1
                continue

            validate_required_accounts(lines, account_ids)
            validate_balanced(lines)
            journal_entry_id = create_journal_entry(conn, transaction, lines, account_ids)
            mark_transaction_posted(conn, transaction["id"], journal_entry_id)
            flag_reason = get_review_flag(transaction, lines)
            if flag_reason:
                flag_transaction_for_review(conn, transaction["id"], flag_reason)
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


def get_unproposed_etsy_transactions(
    conn: sqlite3.Connection,
    period_id: int | None = None,
) -> list[sqlite3.Row]:
    period_filter = ""
    params: list[int] = []
    if period_id is not None:
        period_filter = "AND period_id = ?"
        params.append(period_id)

    return conn.execute(
        f"""
        SELECT *
        FROM etsy_transactions
        WHERE proposed_journal_entry_id IS NULL
          AND posted_at IS NULL
          {period_filter}
        ORDER BY transaction_date, id
        """,
        params,
    ).fetchall()


def get_postable_proposals(
    conn: sqlite3.Connection,
    period_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM proposed_journal_entries
        WHERE period_id = ?
          AND posted_journal_entry_id IS NULL
          AND voided_at IS NULL
          AND status IN ('pending', 'needs_review', 'approved')
          AND entry_type != 'closing'
        ORDER BY entry_date, id
        """,
        (period_id,),
    ).fetchall()


def get_proposed_journal_lines(
    conn: sqlite3.Connection,
    proposed_journal_entry_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM proposed_journal_lines
        WHERE proposed_journal_entry_id = ?
        ORDER BY id
        """,
        (proposed_journal_entry_id,),
    ).fetchall()


def get_uncategorized_proposal_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT pje.id
        FROM proposed_journal_entries pje
        JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
        JOIN accounts a ON a.id = pjl.account_id
        WHERE a.code = ?
          AND pje.posted_journal_entry_id IS NULL
          AND pje.voided_at IS NULL
        ORDER BY pje.id
        """,
        (UNCATEGORIZED_EXPENSE,),
    ).fetchall()

    return [row["id"] for row in rows]


def ensure_journal_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            proposed_journal_entry_id INTEGER,
            closing_batch_id INTEGER,
            entry_date TEXT NOT NULL,
            entry_type TEXT NOT NULL DEFAULT 'regular',
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
    ensure_column(conn, "journal_entries", "period_id", "INTEGER")
    ensure_column(conn, "journal_entries", "proposed_journal_entry_id", "INTEGER")
    ensure_column(conn, "journal_entries", "closing_batch_id", "INTEGER")
    ensure_column(conn, "journal_entries", "entry_type", "TEXT NOT NULL DEFAULT 'regular'")


def ensure_proposed_journal_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS proposed_journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER,
            import_id INTEGER,
            staged_transaction_id INTEGER,
            closing_batch_id INTEGER,
            entry_date TEXT NOT NULL,
            entry_type TEXT NOT NULL DEFAULT 'regular',
            source TEXT NOT NULL,
            source_table TEXT,
            source_id INTEGER,
            memo TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            review_note TEXT,
            flagged_reason TEXT,
            approved_at TEXT,
            voided_at TEXT,
            posted_journal_entry_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_proposed_journal_entries_source_record
        ON proposed_journal_entries(source, source_table, source_id)
        WHERE source_table IS NOT NULL
          AND source_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_proposed_journal_entries_period
        ON proposed_journal_entries(period_id);

        CREATE INDEX IF NOT EXISTS idx_proposed_journal_entries_status
        ON proposed_journal_entries(status);

        CREATE TABLE IF NOT EXISTS proposed_journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposed_journal_entry_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit REAL NOT NULL DEFAULT 0,
            credit REAL NOT NULL DEFAULT 0,
            memo TEXT,
            FOREIGN KEY (proposed_journal_entry_id) REFERENCES proposed_journal_entries(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE INDEX IF NOT EXISTS idx_proposed_journal_lines_entry
        ON proposed_journal_lines(proposed_journal_entry_id);

        CREATE INDEX IF NOT EXISTS idx_proposed_journal_lines_account
        ON proposed_journal_lines(account_id);
        """
    )


def ensure_posting_columns(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "etsy_transactions", "review_status", "TEXT")
    ensure_column(conn, "etsy_transactions", "review_note", "TEXT")
    ensure_column(conn, "etsy_transactions", "flagged_reason", "TEXT")
    ensure_column(conn, "etsy_transactions", "proposed_journal_entry_id", "INTEGER")
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

    if transaction_type == "Deposit":
        return build_deposit_lines(transaction, memo)

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

    if transaction_type == "Marketing":
        return build_expense_or_credit_lines(MARKETING_EXPENSE, net, amount, memo)

    if transaction_type == "Materials Expense":
        return build_cash_expense_lines(MATERIALS_EXPENSE, net, amount, memo)

    if transaction_type == "Supplies Expense":
        return build_cash_expense_lines(SUPPLIES_EXPENSE, net, amount, memo)

    if transaction_type in {"Tax", "VAT"}:
        return build_tax_lines(net, amount, memo)

    if transaction_type == "Payment":
        return build_payment_lines(net, amount, memo)

    return build_expense_or_credit_lines(UNCATEGORIZED_EXPENSE, net, amount, memo)


def build_deposit_lines(transaction: sqlite3.Row, memo: str) -> list[JournalLine]:
    amount = parse_money_from_text(transaction["title"] or "")

    if amount == 0:
        return []

    return [
        JournalLine(CASH, debit=amount, memo=memo),
        JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
    ]


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


def build_cash_expense_lines(
    expense_account_code: str,
    net: float,
    amount: float,
    memo: str,
) -> list[JournalLine]:
    if net < 0:
        return [
            JournalLine(expense_account_code, debit=amount, memo=memo),
            JournalLine(CASH, credit=amount, memo=memo),
        ]

    return [
        JournalLine(CASH, debit=amount, memo=memo),
        JournalLine(expense_account_code, credit=amount, memo=memo),
    ]


def build_tax_lines(net: float, amount: float, memo: str) -> list[JournalLine]:
    if net < 0:
        return [
            JournalLine(SALES_TAX_EXPENSE, debit=amount, memo=memo),
            JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
        ]

    return [
        JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
        JournalLine(SALES_TAX_EXPENSE, credit=amount, memo=memo),
    ]


def build_payment_lines(
    net: float,
    amount: float,
    memo: str,
) -> list[JournalLine]:
    if net > 0:
        return [
            JournalLine(ETSY_CLEARING, debit=amount, memo=memo),
            JournalLine(CASH, credit=amount, memo=memo),
        ]

    return [
        JournalLine(CASH, debit=amount, memo=memo),
        JournalLine(ETSY_CLEARING, credit=amount, memo=memo),
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


def create_journal_entry_from_proposal(
    conn: sqlite3.Connection,
    proposal: sqlite3.Row,
    lines: list[sqlite3.Row],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO journal_entries (
            period_id,
            proposed_journal_entry_id,
            closing_batch_id,
            entry_date,
            entry_type,
            source,
            source_table,
            source_id,
            memo,
            status,
            posted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            proposal["period_id"],
            proposal["id"],
            proposal["closing_batch_id"],
            proposal["entry_date"],
            proposal["entry_type"],
            proposal["source"],
            proposal["source_table"],
            proposal["source_id"],
            proposal["memo"],
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
                line["account_id"],
                line["debit"],
                line["credit"],
                line["memo"],
            ),
        )

    return journal_entry_id


def create_proposed_journal_entry(
    conn: sqlite3.Connection,
    transaction: sqlite3.Row,
    lines: list[JournalLine],
    account_ids: dict[str, int],
    flag_reason: str,
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
            status,
            flagged_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            get_optional_row_value(transaction, "period_id"),
            get_optional_row_value(transaction, "import_id"),
            get_optional_row_value(transaction, "staged_transaction_id"),
            transaction["transaction_date"],
            "regular",
            "etsy",
            "etsy_transactions",
            transaction["id"],
            build_memo(transaction),
            "needs_review" if flag_reason else "pending",
            flag_reason or None,
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


def mark_proposal_posted(
    conn: sqlite3.Connection,
    proposed_journal_entry_id: int,
    journal_entry_id: int,
) -> None:
    conn.execute(
        """
        UPDATE proposed_journal_entries
        SET status = 'posted',
            approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
            posted_journal_entry_id = ?
        WHERE id = ?
        """,
        (journal_entry_id, proposed_journal_entry_id),
    )


def mark_source_transaction_posted(
    conn: sqlite3.Connection,
    proposal: sqlite3.Row,
    journal_entry_id: int,
) -> None:
    if proposal["source_table"] != "etsy_transactions":
        return

    conn.execute(
        """
        UPDATE etsy_transactions
        SET posted_at = CURRENT_TIMESTAMP,
            journal_entry_id = ?,
            review_status = 'posted'
        WHERE id = ?
        """,
        (journal_entry_id, proposal["source_id"]),
    )


def mark_transaction_proposed(
    conn: sqlite3.Connection,
    transaction_id: int,
    proposed_journal_entry_id: int,
    flag_reason: str,
) -> None:
    conn.execute(
        """
        UPDATE etsy_transactions
        SET proposed_journal_entry_id = ?,
            review_status = ?,
            flagged_reason = ?
        WHERE id = ?
        """,
        (
            proposed_journal_entry_id,
            "needs_review" if flag_reason else "pending",
            flag_reason or None,
            transaction_id,
        ),
    )


def mark_linked_etsy_transactions_flagged(
    conn: sqlite3.Connection,
    proposed_journal_entry_ids: list[int],
) -> None:
    if not proposed_journal_entry_ids:
        return

    placeholders = ", ".join("?" for _ in proposed_journal_entry_ids)
    conn.execute(
        f"""
        UPDATE etsy_transactions
        SET review_status = 'needs_review',
            flagged_reason = COALESCE(flagged_reason, ?)
        WHERE proposed_journal_entry_id IN ({placeholders})
        """,
        (UNCATEGORIZED_REVIEW_REASON, *proposed_journal_entry_ids),
    )


def flag_transaction_for_review(
    conn: sqlite3.Connection,
    transaction_id: int,
    reason: str,
) -> None:
    conn.execute(
        """
        UPDATE etsy_transactions
        SET review_status = 'needs_review',
            flagged_reason = ?
        WHERE id = ?
        """,
        (reason, transaction_id),
    )


def get_review_flag(
    transaction: sqlite3.Row,
    lines: list[JournalLine],
) -> str:
    transaction_type = transaction["type"]
    reasons = []

    if transaction_type not in KNOWN_TRANSACTION_TYPES:
        reasons.append(
            f"Unknown Etsy transaction type '{transaction_type}' was posted to Uncategorized Expense."
        )

    if transaction_type == "Deposit" and not lines:
        reasons.append("Deposit row did not include a usable dollar amount in the title.")

    line_reason = get_line_review_flag(lines)
    if line_reason:
        reasons.append(line_reason)

    return " ".join(reasons)


def get_line_review_flag(lines: list[JournalLine]) -> str:
    if any(line.account_code == UNCATEGORIZED_EXPENSE for line in lines):
        return UNCATEGORIZED_REVIEW_REASON

    return ""


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


def validate_balanced_rows(lines: list[sqlite3.Row]) -> None:
    total_debits = round(sum(float(line["debit"] or 0) for line in lines), 2)
    total_credits = round(sum(float(line["credit"] or 0) for line in lines), 2)

    if total_debits != total_credits:
        raise ValueError(
            f"Proposed journal entry is not balanced: debits={total_debits}, "
            f"credits={total_credits}"
        )


def build_memo(transaction: sqlite3.Row) -> str:
    details = [transaction["type"], transaction["title"], transaction["info"]]
    return " - ".join(str(detail).strip() for detail in details if detail)


def get_optional_row_value(row: sqlite3.Row, key: str) -> object | None:
    return row[key] if key in row.keys() else None


def parse_money_from_text(text: str) -> float:
    match = re.search(r"\$([0-9,]+(?:\.[0-9]{2})?)", text)

    if not match:
        return 0.0

    return round(float(match.group(1).replace(",", "")), 2)


if __name__ == "__main__":
    summary = post_etsy_transactions()
    print(
        f"Posted {summary.posted} journal entries, skipped {summary.skipped} "
        f"zero-dollar rows out of {summary.total_unposted} unposted Etsy rows."
    )
