import sqlite3
from pathlib import Path
from typing import Any

try:
    from ..reports import get_income_statement as build_income_statement_report
    from ..reports import get_trial_balance as build_trial_balance_report
except ImportError:
    from reports import get_income_statement as build_income_statement_report
    from reports import get_trial_balance as build_trial_balance_report


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "db" / "accounting.db"


def get_period_summary(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        period = get_period_row(conn, period_id)
        import_summary = conn.execute(
            """
            SELECT
                COUNT(*) AS import_count,
                COALESCE(SUM(row_count), 0) AS imported_rows
            FROM imports
            WHERE period_id = ?
            """,
            (period_id,),
        ).fetchone()
        proposed_summary = conn.execute(
            """
            SELECT
                COUNT(*) AS proposed_entries,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_entries,
                SUM(CASE WHEN flagged_reason IS NOT NULL THEN 1 ELSE 0 END) AS flagged_entries,
                SUM(CASE WHEN posted_journal_entry_id IS NOT NULL THEN 1 ELSE 0 END) AS posted_proposals
            FROM proposed_journal_entries
            WHERE period_id = ?
              AND voided_at IS NULL
              AND status != 'voided'
            """,
            (period_id,),
        ).fetchone()
        ledger_summary = conn.execute(
            """
            SELECT COUNT(*) AS posted_ledger_entries
            FROM journal_entries
            WHERE period_id = ?
              AND status = 'posted'
            """,
            (period_id,),
        ).fetchone()

    return {
        "period": format_period(period),
        "imports": {
            "importCount": import_summary["import_count"] or 0,
            "importedRows": import_summary["imported_rows"] or 0,
        },
        "journal": {
            "proposedEntries": proposed_summary["proposed_entries"] or 0,
            "pendingEntries": proposed_summary["pending_entries"] or 0,
            "flaggedEntries": proposed_summary["flagged_entries"] or 0,
            "postedProposals": proposed_summary["posted_proposals"] or 0,
            "postedLedgerEntries": ledger_summary["posted_ledger_entries"] or 0,
        },
    }


def get_trial_balance(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        get_period_row(conn, period_id)

    return build_trial_balance_report(db_path, period_id=period_id)


def get_income_statement(
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        period = get_period_row(conn, period_id)

    return build_income_statement_report(
        period["period_start"],
        period["period_end"],
        db_path,
        period_id,
    )


def get_monthly_income_summary(
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 24,
) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        periods = conn.execute(
            """
            SELECT
                id,
                period_start,
                period_end,
                label,
                status,
                reviewed_at,
                adjusted_at,
                closed_at
            FROM accounting_periods
            ORDER BY period_start DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    summaries = []

    for period in periods:
        statement = build_income_statement_report(
            period["period_start"],
            period["period_end"],
            db_path,
            period["id"],
        )
        totals = statement["totals"]
        summaries.append(
            {
                "period": format_period(period),
                "totalRevenue": totals["total_revenue"],
                "netRevenue": totals["net_revenue"],
                "totalExpenses": totals["total_expenses"],
                "netIncome": totals["net_income"],
            }
        )

    return {
        "periods": summaries,
        "totals": {
            "totalRevenue": round(
                sum(period["totalRevenue"] for period in summaries),
                2,
            ),
            "netRevenue": round(
                sum(period["netRevenue"] for period in summaries),
                2,
            ),
            "totalExpenses": round(
                sum(period["totalExpenses"] for period in summaries),
                2,
            ),
            "netIncome": round(
                sum(period["netIncome"] for period in summaries),
                2,
            ),
        },
    }


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_period_row(conn: sqlite3.Connection, period_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT
            id,
            period_start,
            period_end,
            label,
            status,
            reviewed_at,
            adjusted_at,
            closed_at
        FROM accounting_periods
        WHERE id = ?
        LIMIT 1
        """,
        (period_id,),
    ).fetchone()

    if row is None:
        raise ValueError("Accounting period was not found.")

    return row


def format_period(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "periodStart": row["period_start"],
        "periodEnd": row["period_end"],
        "label": row["label"],
        "status": row["status"],
        "reviewedAt": row["reviewed_at"],
        "adjustedAt": row["adjusted_at"],
        "closedAt": row["closed_at"],
        "trialBalanceConfirmed": row["reviewed_at"] is not None,
    }
