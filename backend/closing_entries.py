import sqlite3
from pathlib import Path
from typing import Any

try:
    from .models import JournalLine, LedgerPostSummary
    from .post_transacs import (
        create_journal_entry_from_proposal,
        ensure_journal_tables,
        ensure_proposed_journal_tables,
        get_account_ids,
        get_proposed_journal_lines,
        mark_proposal_posted,
        validate_balanced,
        validate_balanced_rows,
        validate_required_accounts,
    )
except ImportError:
    from models import JournalLine, LedgerPostSummary
    from post_transacs import (
        create_journal_entry_from_proposal,
        ensure_journal_tables,
        ensure_proposed_journal_tables,
        get_account_ids,
        get_proposed_journal_lines,
        mark_proposal_posted,
        validate_balanced,
        validate_balanced_rows,
        validate_required_accounts,
    )


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
CAPITAL = "3000"
INCOME_SUMMARY = "3900"
TEMPORARY_ACCOUNT_TYPES = ("revenue", "contra_revenue", "expense")


def generate_closing_entries(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_closing_tables(conn)
        ensure_journal_tables(conn)
        ensure_proposed_journal_tables(conn)

        period = get_period(conn, period_id)
        batch_id = get_or_create_draft_closing_batch(conn, period_id)
        clear_unposted_closing_proposals(conn, batch_id)

        account_ids = get_account_ids(conn)
        balances = get_temporary_account_balances(conn, period_id)
        closing_date = period["period_end"]
        generated_entry_ids = []

        (
            revenue_lines,
            gross_revenue_total,
            contra_revenue_total,
            net_revenue,
        ) = build_revenue_closing_lines(balances)
        if revenue_lines:
            generated_entry_ids.append(
                create_closing_proposal(
                    conn,
                    period_id,
                    batch_id,
                    closing_date,
                    "Close revenues to Income Summary",
                    revenue_lines,
                    account_ids,
                )
            )

        expense_lines, expense_total = build_expense_closing_lines(balances)
        if expense_lines:
            generated_entry_ids.append(
                create_closing_proposal(
                    conn,
                    period_id,
                    batch_id,
                    closing_date,
                    "Close expenses to Income Summary",
                    expense_lines,
                    account_ids,
                )
            )

        net_income = round(net_revenue - expense_total, 2)
        capital_lines = build_income_summary_closing_lines(net_income)
        if capital_lines:
            generated_entry_ids.append(
                create_closing_proposal(
                    conn,
                    period_id,
                    batch_id,
                    closing_date,
                    "Close Income Summary to Capital",
                    capital_lines,
                    account_ids,
                )
            )

    return {
        "periodId": period_id,
        "closingBatchId": batch_id,
        "generatedEntries": len(generated_entry_ids),
        "generatedEntryIds": generated_entry_ids,
        "totalRevenues": gross_revenue_total,
        "totalContraRevenues": contra_revenue_total,
        "netRevenue": net_revenue,
        "totalExpenses": expense_total,
        "netIncome": net_income,
    }


def get_closing_entry_ids(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[int]:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_closing_tables(conn)
        ensure_proposed_journal_tables(conn)

        rows = conn.execute(
            """
            SELECT id
            FROM proposed_journal_entries
            WHERE period_id = ?
              AND entry_type = 'closing'
              AND voided_at IS NULL
              AND status IN ('pending', 'needs_review', 'approved', 'posted')
            ORDER BY id
            """,
            (period_id,),
        ).fetchall()

    return [row["id"] for row in rows]


def post_closing_entries(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> LedgerPostSummary:
    db_file = Path(db_path)

    with sqlite3.connect(db_file) as conn:
        conn.row_factory = sqlite3.Row
        ensure_closing_tables(conn)
        ensure_journal_tables(conn)
        ensure_proposed_journal_tables(conn)

        proposals = get_postable_closing_proposals(conn, period_id)
        posted = 0
        skipped = 0
        posted_batch_ids: set[int] = set()

        for proposal in proposals:
            lines = get_proposed_journal_lines(conn, proposal["id"])

            if not lines:
                skipped += 1
                continue

            validate_balanced_rows(lines)
            journal_entry_id = create_journal_entry_from_proposal(conn, proposal, lines)
            mark_proposal_posted(conn, proposal["id"], journal_entry_id)

            if proposal["closing_batch_id"] is not None:
                posted_batch_ids.add(proposal["closing_batch_id"])

            posted += 1

        for batch_id in posted_batch_ids:
            conn.execute(
                """
                UPDATE closing_batches
                SET status = 'posted',
                    approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
                    posted_at = COALESCE(posted_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (batch_id,),
            )

        mark_period_closed(conn, period_id)

    return LedgerPostSummary(
        posted=posted,
        skipped=skipped,
        total_proposals=len(proposals),
    )


def get_postable_closing_proposals(
    conn: sqlite3.Connection,
    period_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM proposed_journal_entries
        WHERE period_id = ?
          AND entry_type = 'closing'
          AND posted_journal_entry_id IS NULL
          AND voided_at IS NULL
          AND status IN ('pending', 'needs_review', 'approved')
        ORDER BY entry_date, id
        """,
        (period_id,),
    ).fetchall()


def mark_period_closed(conn: sqlite3.Connection, period_id: int) -> None:
    conn.execute(
        """
        UPDATE accounting_periods
        SET status = 'closed',
            closing_confirmed_at = COALESCE(closing_confirmed_at, CURRENT_TIMESTAMP),
            closed_at = COALESCE(closed_at, CURRENT_TIMESTAMP)
        WHERE id = ?
        """,
        (period_id,),
    )


def ensure_closing_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS closing_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            posted_at TEXT,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_closing_batches_period
        ON closing_batches(period_id)
        """
    )


def get_period(conn: sqlite3.Connection, period_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT id, period_start, period_end, label, status
        FROM accounting_periods
        WHERE id = ?
        """,
        (period_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Accounting period {period_id} does not exist.")

    return row


def get_or_create_draft_closing_batch(
    conn: sqlite3.Connection,
    period_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT id, status
        FROM closing_batches
        WHERE period_id = ?
        """,
        (period_id,),
    ).fetchone()

    if row is not None:
        if row["status"] == "posted":
            raise ValueError("Closing entries have already been posted for this period.")

        conn.execute(
            """
            UPDATE closing_batches
            SET status = 'draft',
                generated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["id"],),
        )
        return row["id"]

    cursor = conn.execute(
        """
        INSERT INTO closing_batches (period_id, status)
        VALUES (?, 'draft')
        """,
        (period_id,),
    )
    return cursor.lastrowid


def clear_unposted_closing_proposals(
    conn: sqlite3.Connection,
    batch_id: int,
) -> None:
    posted_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM proposed_journal_entries
        WHERE closing_batch_id = ?
          AND posted_journal_entry_id IS NOT NULL
        """,
        (batch_id,),
    ).fetchone()[0]

    if posted_count:
        raise ValueError("Closing entries for this batch have already been posted.")

    proposal_ids = [
        row["id"]
        for row in conn.execute(
            """
            SELECT id
            FROM proposed_journal_entries
            WHERE closing_batch_id = ?
            """,
            (batch_id,),
        ).fetchall()
    ]

    if not proposal_ids:
        return

    placeholders = ", ".join("?" for _ in proposal_ids)
    conn.execute(
        f"""
        DELETE FROM proposed_journal_lines
        WHERE proposed_journal_entry_id IN ({placeholders})
        """,
        proposal_ids,
    )
    conn.execute(
        f"""
        DELETE FROM proposed_journal_entries
        WHERE id IN ({placeholders})
        """,
        proposal_ids,
    )


def get_temporary_account_balances(
    conn: sqlite3.Connection,
    period_id: int,
) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in TEMPORARY_ACCOUNT_TYPES)
    return conn.execute(
        f"""
        SELECT
            a.code AS account_code,
            a.name AS account_name,
            a.account_type,
            a.normal_balance,
            ROUND(COALESCE(SUM(jl.debit), 0), 2) AS debits,
            ROUND(COALESCE(SUM(jl.credit), 0), 2) AS credits
        FROM accounts a
        JOIN journal_lines jl ON jl.account_id = a.id
        JOIN journal_entries je ON je.id = jl.journal_entry_id
        WHERE je.period_id = ?
          AND je.status = 'posted'
          AND je.entry_type != 'closing'
          AND a.account_type IN ({placeholders})
          AND a.is_active = 1
        GROUP BY
            a.id,
            a.code,
            a.name,
            a.account_type,
            a.normal_balance
        ORDER BY a.code
        """,
        (period_id, *TEMPORARY_ACCOUNT_TYPES),
    ).fetchall()


def build_revenue_closing_lines(
    balances: list[sqlite3.Row],
) -> tuple[list[JournalLine], float, float, float]:
    lines: list[JournalLine] = []
    revenue_total = 0.0
    contra_revenue_total = 0.0

    for account in balances:
        amount = 0.0
        if account["account_type"] == "revenue":
            amount = round(float(account["credits"] or 0) - float(account["debits"] or 0), 2)
            if amount <= 0:
                continue

            lines.append(
                JournalLine(
                    account["account_code"],
                    debit=amount,
                    memo="Close revenue account",
                )
            )
            revenue_total = round(revenue_total + amount, 2)

        if account["account_type"] == "contra_revenue":
            amount = round(float(account["debits"] or 0) - float(account["credits"] or 0), 2)
            if amount <= 0:
                continue

            lines.append(
                JournalLine(
                    account["account_code"],
                    credit=amount,
                    memo="Close contra-revenue account",
                )
            )
            contra_revenue_total = round(contra_revenue_total + amount, 2)

    net_revenue = round(revenue_total - contra_revenue_total, 2)
    if net_revenue > 0:
        lines.append(
            JournalLine(
                INCOME_SUMMARY,
                credit=net_revenue,
                memo="Close net revenue to Income Summary",
            )
        )
    elif net_revenue < 0:
        lines.append(
            JournalLine(
                INCOME_SUMMARY,
                debit=abs(net_revenue),
                memo="Close net revenue loss to Income Summary",
            )
        )

    return lines, revenue_total, contra_revenue_total, net_revenue


def build_expense_closing_lines(
    balances: list[sqlite3.Row],
) -> tuple[list[JournalLine], float]:
    account_lines: list[JournalLine] = []
    total = 0.0

    for account in balances:
        if account["account_type"] != "expense":
            continue

        amount = round(float(account["debits"] or 0) - float(account["credits"] or 0), 2)
        if amount == 0:
            continue

        if amount > 0:
            account_lines.append(
                JournalLine(
                    account["account_code"],
                    credit=amount,
                    memo="Close expense account",
                )
            )
        else:
            account_lines.append(
                JournalLine(
                    account["account_code"],
                    debit=abs(amount),
                    memo="Close negative expense account",
                )
            )
        total = round(total + amount, 2)

    if not account_lines:
        return [], 0.0

    if total > 0:
        income_summary_line = JournalLine(
            INCOME_SUMMARY,
            debit=total,
            memo="Close expenses to Income Summary",
        )
    elif total < 0:
        income_summary_line = JournalLine(
            INCOME_SUMMARY,
            credit=abs(total),
            memo="Close negative expenses to Income Summary",
        )
    else:
        return account_lines, 0.0

    return [income_summary_line, *account_lines], total


def build_income_summary_closing_lines(net_income: float) -> list[JournalLine]:
    if net_income > 0:
        return [
            JournalLine(
                INCOME_SUMMARY,
                debit=net_income,
                memo="Close net income to Capital",
            ),
            JournalLine(
                CAPITAL,
                credit=net_income,
                memo="Close net income to Capital",
            ),
        ]

    if net_income < 0:
        net_loss = abs(net_income)
        return [
            JournalLine(
                CAPITAL,
                debit=net_loss,
                memo="Close net loss to Capital",
            ),
            JournalLine(
                INCOME_SUMMARY,
                credit=net_loss,
                memo="Close net loss to Capital",
            ),
        ]

    return []


def create_closing_proposal(
    conn: sqlite3.Connection,
    period_id: int,
    batch_id: int,
    entry_date: str,
    memo: str,
    lines: list[JournalLine],
    account_ids: dict[str, int],
) -> int:
    validate_required_accounts(lines, account_ids)
    validate_balanced(lines)

    cursor = conn.execute(
        """
        INSERT INTO proposed_journal_entries (
            period_id,
            closing_batch_id,
            entry_date,
            entry_type,
            source,
            memo,
            status
        )
        VALUES (?, ?, ?, 'closing', 'closing', ?, 'pending')
        """,
        (period_id, batch_id, entry_date, memo),
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
