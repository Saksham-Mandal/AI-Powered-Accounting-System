
import json
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"
DEFAULT_PERIOD_START = "2026-01-01"
DEFAULT_PERIOD_END = "2026-01-31"


def get_trial_balance(
    db_path: str | Path = DEFAULT_DB_PATH,
    include_closing_entries: bool = False,
    period_id: int | None = None,
) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if has_unposted_proposed_entries(conn, period_id):
            rows = get_trial_balance_rows_from_proposals(conn, period_id)
        else:
            rows = get_trial_balance_rows_from_ledger(
                conn,
                include_closing_entries=include_closing_entries,
                period_id=period_id,
            )

    lines = [format_trial_balance_line(row) for row in rows]
    total_debit_balances = round(sum(line["debit_balance"] for line in lines), 2)
    total_credit_balances = round(sum(line["credit_balance"] for line in lines), 2)

    return {
        "lines": lines,
        "total_debit_balances": total_debit_balances,
        "total_credit_balances": total_credit_balances,
        "is_balanced": total_debit_balances == total_credit_balances,
    }


def has_unposted_proposed_entries(
    conn: sqlite3.Connection,
    period_id: int | None = None,
) -> bool:
    if not table_exists(conn, "proposed_journal_entries"):
        return False

    period_filter = ""
    params: list[int] = []
    if period_id is not None:
        period_filter = "AND period_id = ?"
        params.append(period_id)

    row = conn.execute(
        f"""
        SELECT 1
        FROM proposed_journal_entries
        WHERE posted_journal_entry_id IS NULL
          AND voided_at IS NULL
          AND status IN ('pending', 'needs_review', 'approved')
          AND entry_type != 'closing'
          {period_filter}
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row is not None


def get_trial_balance_rows_from_proposals(
    conn: sqlite3.Connection,
    period_id: int | None = None,
) -> list[sqlite3.Row]:
    period_join_filter = ""
    params: list[int] = []
    if period_id is not None:
        period_join_filter = "AND pje.period_id = ?"
        params.append(period_id)

    return conn.execute(
        f"""
        SELECT
            a.code AS account_code,
            a.name AS account_name,
            a.account_type,
            a.normal_balance,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN pje.id IS NOT NULL THEN pjl.debit ELSE 0 END),
                    0
                ),
                2
            ) AS debits,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN pje.id IS NOT NULL THEN pjl.credit ELSE 0 END),
                    0
                ),
                2
            ) AS credits
        FROM accounts a
        LEFT JOIN proposed_journal_lines pjl ON pjl.account_id = a.id
        LEFT JOIN proposed_journal_entries pje
            ON pje.id = pjl.proposed_journal_entry_id
           AND pje.posted_journal_entry_id IS NULL
           AND pje.voided_at IS NULL
           AND pje.status IN ('pending', 'needs_review', 'approved')
           AND pje.entry_type != 'closing'
           {period_join_filter}
        WHERE a.is_active = 1
        GROUP BY
            a.id,
            a.code,
            a.name,
            a.account_type,
            a.normal_balance
        ORDER BY a.code
        """,
        params,
    ).fetchall()


def get_trial_balance_rows_from_ledger(
    conn: sqlite3.Connection,
    include_closing_entries: bool = False,
    period_id: int | None = None,
) -> list[sqlite3.Row]:
    closing_join_filter = "" if include_closing_entries else "AND je.entry_type != 'closing'"
    period_join_filter = ""
    params: list[int] = []
    if period_id is not None:
        period_join_filter = "AND je.period_id = ?"
        params.append(period_id)

    return conn.execute(
        f"""
        SELECT
            a.code AS account_code,
            a.name AS account_name,
            a.account_type,
            a.normal_balance,
            ROUND(
                COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.debit ELSE 0 END), 0),
                2
            ) AS debits,
            ROUND(
                COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.credit ELSE 0 END), 0),
                2
            ) AS credits
        FROM accounts a
        LEFT JOIN journal_lines jl ON jl.account_id = a.id
        LEFT JOIN journal_entries je
            ON je.id = jl.journal_entry_id
           AND je.status = 'posted'
           {closing_join_filter}
           {period_join_filter}
        WHERE a.is_active = 1
        GROUP BY
            a.id,
            a.code,
            a.name,
            a.account_type,
            a.normal_balance
        ORDER BY a.code
        """,
        params,
    ).fetchall()


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def get_income_statement(
    start_date: str = DEFAULT_PERIOD_START,
    end_date: str = DEFAULT_PERIOD_END,
    db_path: str | Path = DEFAULT_DB_PATH,
    period_id: int | None = None,
) -> dict[str, Any]:
    balances = get_account_balances(
        db_path,
        start_date=start_date,
        end_date=end_date,
        include_closing_entries=False,
        period_id=period_id,
    )

    revenue_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "revenue" and account["statement_amount"] != 0
    ]
    contra_revenue_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "contra_revenue"
        and account["statement_amount"] != 0
    ]
    expense_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "expense" and account["statement_amount"] != 0
    ]

    total_revenue = round(sum(line["amount"] for line in revenue_lines), 2)
    total_contra_revenue = round(
        sum(line["amount"] for line in contra_revenue_lines),
        2,
    )
    net_revenue = round(total_revenue - total_contra_revenue, 2)
    total_expenses = round(sum(line["amount"] for line in expense_lines), 2)
    net_income = round(net_revenue - total_expenses, 2)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "sections": {
            "revenue": revenue_lines,
            "contra_revenue": contra_revenue_lines,
            "expenses": expense_lines,
        },
        "totals": {
            "total_revenue": total_revenue,
            "total_contra_revenue": total_contra_revenue,
            "net_revenue": net_revenue,
            "total_expenses": total_expenses,
            "net_income": net_income,
        },
    }


def save_income_statement_snapshot(
    period_id: int,
    period_start: str,
    period_end: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    statement = get_income_statement(period_start, period_end, db_path, period_id)
    totals = statement["totals"]

    with sqlite3.connect(db_path) as conn:
        ensure_income_statement_snapshots_table(conn)
        conn.execute(
            """
            INSERT INTO income_statement_snapshots (
                period_id,
                period_start,
                period_end,
                total_revenue,
                total_contra_revenue,
                net_revenue,
                total_expenses,
                net_income,
                statement_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_id) DO UPDATE SET
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                total_revenue = excluded.total_revenue,
                total_contra_revenue = excluded.total_contra_revenue,
                net_revenue = excluded.net_revenue,
                total_expenses = excluded.total_expenses,
                net_income = excluded.net_income,
                statement_json = excluded.statement_json,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                period_id,
                period_start,
                period_end,
                totals["total_revenue"],
                totals["total_contra_revenue"],
                totals["net_revenue"],
                totals["total_expenses"],
                totals["net_income"],
                json.dumps(statement),
            ),
        )
        conn.execute(
            """
            UPDATE accounting_periods
            SET statements_generated_at = COALESCE(
                statements_generated_at,
                CURRENT_TIMESTAMP
            )
            WHERE id = ?
            """,
            (period_id,),
        )

    return statement


def get_income_statement_snapshots(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_income_statement_snapshots_table(conn)
        rows = conn.execute(
            """
            SELECT
                iss.id,
                iss.period_id,
                iss.period_start,
                iss.period_end,
                iss.total_revenue,
                iss.total_contra_revenue,
                iss.net_revenue,
                iss.total_expenses,
                iss.net_income,
                iss.statement_json,
                iss.created_at,
                ap.label AS period_label
            FROM income_statement_snapshots iss
            LEFT JOIN accounting_periods ap ON ap.id = iss.period_id
            ORDER BY iss.period_start DESC, iss.id DESC
            """
        ).fetchall()

    snapshots = []
    for row in rows:
        statement = json.loads(row["statement_json"])
        snapshots.append(
            {
                "id": row["id"],
                "periodId": row["period_id"],
                "periodStart": row["period_start"],
                "periodEnd": row["period_end"],
                "periodLabel": row["period_label"],
                "totalRevenue": row["total_revenue"],
                "totalContraRevenue": row["total_contra_revenue"],
                "netRevenue": row["net_revenue"],
                "totalExpenses": row["total_expenses"],
                "netIncome": row["net_income"],
                "createdAt": row["created_at"],
                "statement": statement,
            }
        )

    return snapshots


def ensure_income_statement_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_statement_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id INTEGER NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_revenue REAL NOT NULL DEFAULT 0,
            total_contra_revenue REAL NOT NULL DEFAULT 0,
            net_revenue REAL NOT NULL DEFAULT 0,
            total_expenses REAL NOT NULL DEFAULT 0,
            net_income REAL NOT NULL DEFAULT 0,
            statement_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (period_id) REFERENCES accounting_periods(id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_income_statement_snapshots_period
        ON income_statement_snapshots(period_id)
        """
    )


def get_balance_sheet(
    as_of_date: str = DEFAULT_PERIOD_END,
    period_start: str = DEFAULT_PERIOD_START,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    balances = get_account_balances(db_path, end_date=as_of_date)

    asset_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "asset"
    ]
    liability_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "liability"
    ]
    equity_lines = [
        format_statement_line(account)
        for account in balances
        if account["account_type"] == "equity"
        and account["account_code"] != "3900"
    ]

    total_assets = round(sum(line["amount"] for line in asset_lines), 2)
    total_liabilities = round(sum(line["amount"] for line in liability_lines), 2)
    total_equity = round(sum(line["amount"] for line in equity_lines), 2)
    total_liabilities_and_equity = round(total_liabilities + total_equity, 2)

    return {
        "as_of_date": as_of_date,
        "sections": {
            "assets": asset_lines,
            "liabilities": liability_lines,
            "equity": equity_lines,
        },
        "totals": {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "total_liabilities_and_equity": total_liabilities_and_equity,
        },
        "is_balanced": total_assets == total_liabilities_and_equity,
    }


def get_account_balances(
    db_path: str | Path = DEFAULT_DB_PATH,
    start_date: str | None = None,
    end_date: str | None = None,
    include_closing_entries: bool = True,
    period_id: int | None = None,
) -> list[dict[str, Any]]:
    join_clauses = ["je.status = 'posted'"]
    params: list[str | int] = []

    if not include_closing_entries:
        join_clauses.append("je.entry_type != 'closing'")

    if start_date is not None:
        join_clauses.append("je.entry_date >= ?")
        params.append(start_date)

    if end_date is not None:
        join_clauses.append("je.entry_date <= ?")
        params.append(end_date)

    if period_id is not None:
        join_clauses.append("je.period_id = ?")
        params.append(period_id)

    journal_entry_filter = " AND ".join(join_clauses)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
                a.code AS account_code,
                a.name AS account_name,
                a.account_type,
                a.normal_balance,
                ROUND(
                    COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.debit ELSE 0 END), 0),
                    2
                ) AS debits,
                ROUND(
                    COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.credit ELSE 0 END), 0),
                    2
                ) AS credits
            FROM accounts a
            LEFT JOIN journal_lines jl ON jl.account_id = a.id
            LEFT JOIN journal_entries je
                ON je.id = jl.journal_entry_id
               AND {journal_entry_filter}
            WHERE a.is_active = 1
            GROUP BY
                a.id,
                a.code,
                a.name,
                a.account_type,
                a.normal_balance
            ORDER BY a.code
            """,
            params,
        ).fetchall()

    return [format_account_balance(row) for row in rows]


def format_trial_balance_line(row: sqlite3.Row) -> dict[str, Any]:
    debits = float(row["debits"] or 0)
    credits = float(row["credits"] or 0)
    balance = round(debits - credits, 2)

    return {
        "account_code": row["account_code"],
        "account_name": row["account_name"],
        "account_type": row["account_type"],
        "normal_balance": row["normal_balance"],
        "debits": debits,
        "credits": credits,
        "debit_balance": balance if balance > 0 else 0,
        "credit_balance": abs(balance) if balance < 0 else 0,
    }


def format_account_balance(row: sqlite3.Row) -> dict[str, Any]:
    debits = float(row["debits"] or 0)
    credits = float(row["credits"] or 0)
    account_type = row["account_type"]

    if account_type in {"asset", "expense", "contra_revenue"}:
        statement_amount = round(debits - credits, 2)
    else:
        statement_amount = round(credits - debits, 2)

    return {
        "account_code": row["account_code"],
        "account_name": row["account_name"],
        "account_type": account_type,
        "normal_balance": row["normal_balance"],
        "debits": debits,
        "credits": credits,
        "statement_amount": statement_amount,
    }


def format_statement_line(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_code": account["account_code"],
        "account_name": account["account_name"],
        "account_type": account["account_type"],
        "amount": account["statement_amount"],
    }


if __name__ == "__main__":
    trial_balance = get_trial_balance()
    income_statement = get_income_statement()
    balance_sheet = get_balance_sheet()

    print(f"Balanced: {trial_balance['is_balanced']}")
    print(f"Debit balances: {trial_balance['total_debit_balances']:.2f}")
    print(f"Credit balances: {trial_balance['total_credit_balances']:.2f}")
    print(f"Net income: {income_statement['totals']['net_income']:.2f}")
    print(f"Assets: {balance_sheet['totals']['total_assets']:.2f}")
    print(
        "Liabilities + Equity: "
        f"{balance_sheet['totals']['total_liabilities_and_equity']:.2f}"
    )
