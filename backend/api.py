import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

try:
    from .agent.schemas import AgentChatRequest, AgentChatResponse
    from .agent.service import run_agent_chat
    from .closing_entries import (
        generate_closing_entries,
        get_closing_entry_ids,
        post_closing_entries,
    )
    from .csv_parser import import_etsy_csv_content
    from .db.cleardb import rollback_period
    from .models import JournalLine
    from .post_transacs import (
        create_manual_proposed_entry,
        flag_uncategorized_proposals,
        post_approved_proposals,
        propose_etsy_transactions,
        void_proposed_entry,
    )
    from .reports import (
        get_balance_sheet,
        get_income_statement,
        get_income_statement_snapshots,
        get_latest_balance_sheet_snapshot,
        get_trial_balance,
        save_balance_sheet_snapshot,
        save_income_statement_snapshot,
    )
    from .transaction_csv_parser import import_transaction_csv_content
    from .var_cost import (
        build_monthly_variable_cost_transaction_rows_from_content,
        serialize_transaction_csv,
    )
except ImportError:
    from agent.schemas import AgentChatRequest, AgentChatResponse
    from agent.service import run_agent_chat
    from closing_entries import (
        generate_closing_entries,
        get_closing_entry_ids,
        post_closing_entries,
    )
    from csv_parser import import_etsy_csv_content
    from db.cleardb import rollback_period
    from models import JournalLine
    from post_transacs import (
        create_manual_proposed_entry,
        flag_uncategorized_proposals,
        post_approved_proposals,
        propose_etsy_transactions,
        void_proposed_entry,
    )
    from reports import (
        get_balance_sheet,
        get_income_statement,
        get_income_statement_snapshots,
        get_latest_balance_sheet_snapshot,
        get_trial_balance,
        save_balance_sheet_snapshot,
        save_income_statement_snapshot,
    )
    from transaction_csv_parser import import_transaction_csv_content
    from var_cost import (
        build_monthly_variable_cost_transaction_rows_from_content,
        serialize_transaction_csv,
    )


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "accounting.db"
VARIABLE_COST_CSV_PATH = (
    BASE_DIR / "csv_files" / "Variable Non-Etsy Expense Estimate - Sheet1.csv"
)

app = FastAPI(title="EZPrntz Accounting API")

CURRENT_PERIOD = {
    "period_start": "2026-01-01",
    "period_end": "2026-01-31",
    "label": "January 2026",
}
MIN_FINALIZATION_DELAY_DAYS = 14
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_NAMES_BY_NUMBER = {
    month_number: month_name.title()
    for month_name, month_number in MONTH_NAMES.items()
}


class ManualJournalLineRequest(BaseModel):
    accountCode: str = Field(min_length=1)
    debit: float = 0
    credit: float = 0
    memo: str = ""


class ManualJournalEntryRequest(BaseModel):
    entryDate: str = Field(min_length=1)
    memo: str = Field(min_length=1)
    lines: list[ManualJournalLineRequest]


class VoidProposedEntryRequest(BaseModel):
    reason: str = Field(min_length=1)
    note: str = ""


class PeriodRequest(BaseModel):
    month: str = Field(min_length=1)
    year: int


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/periods")
def get_accounting_periods() -> list[dict[str, Any]]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        rows = conn.execute(
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
            """
        ).fetchall()

    return [format_period(row) for row in rows]


@app.post("/api/periods")
def create_accounting_period(request: PeriodRequest) -> dict[str, Any]:
    with get_connection() as conn:
        period = get_or_create_import_period(conn, request.month, request.year)

    return format_period(period)


@app.get("/api/periods/{period_id}")
def get_accounting_period(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    return format_period(period)


@app.delete("/api/periods/{period_id}/rollback")
def rollback_accounting_period(period_id: int) -> dict[str, Any]:
    try:
        deleted_counts = rollback_period(period_id, DB_PATH)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return {
        "periodId": deleted_counts["period_id"],
        "periodLabel": deleted_counts["period_label"],
        "deleted": deleted_counts,
    }


@app.get("/api/periods/{period_id}/reports/trial-balance")
def get_period_trial_balance_report(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        get_period_row_by_id(conn, period_id)

    return get_trial_balance(DB_PATH, period_id=period_id)


@app.get("/api/periods/{period_id}/reports/post-closing-trial-balance")
def get_period_post_closing_trial_balance_report(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        get_period_row_by_id(conn, period_id)

    return get_trial_balance(
        DB_PATH,
        include_closing_entries=True,
        period_id=period_id,
    )


@app.get("/api/periods/{period_id}/reports/income-statement")
def get_period_income_statement_report(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    return get_income_statement(
        period["period_start"],
        period["period_end"],
        DB_PATH,
        period_id,
    )


@app.get("/api/periods/{period_id}/reports/balance-sheet")
def get_period_balance_sheet_report(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    return get_balance_sheet(
        period["period_end"],
        period["period_start"],
        DB_PATH,
    )


@app.get("/api/reports/trial-balance")
def get_trial_balance_report() -> dict[str, Any]:
    return get_trial_balance(DB_PATH)


@app.get("/api/reports/post-closing-trial-balance")
def get_post_closing_trial_balance_report() -> dict[str, Any]:
    return get_trial_balance(DB_PATH, include_closing_entries=True)


@app.get("/api/reports/income-statement")
def get_income_statement_report() -> dict[str, Any]:
    return get_income_statement(
        CURRENT_PERIOD["period_start"],
        CURRENT_PERIOD["period_end"],
        DB_PATH,
    )


@app.get("/api/reports/income-statements")
def get_saved_income_statement_reports() -> list[dict[str, Any]]:
    return get_income_statement_snapshots(DB_PATH)


@app.get("/api/reports/balance-sheet")
def get_balance_sheet_report() -> dict[str, Any]:
    return get_balance_sheet(
        CURRENT_PERIOD["period_end"],
        CURRENT_PERIOD["period_start"],
        DB_PATH,
    )


@app.get("/api/reports/balance-sheet/latest")
def get_latest_saved_balance_sheet_report() -> dict[str, Any]:
    snapshot = get_latest_balance_sheet_snapshot(DB_PATH)

    if snapshot is not None:
        return snapshot

    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_latest_closed_period_row(conn)

    save_balance_sheet_snapshot(
        period["id"],
        period["period_end"],
        DB_PATH,
    )
    snapshot = get_latest_balance_sheet_snapshot(DB_PATH)

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No saved balance sheet is available yet.",
        )

    return snapshot


@app.get("/api/periods/current")
def get_current_period() -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        row = get_current_period_row(conn)

    return format_period(row)


@app.post("/api/periods/{period_id}/confirm-trial-balance")
def confirm_period_trial_balance(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    ensure_period_is_ready_to_finalize(period)

    try:
        post_summary = post_approved_proposals(period["id"], DB_PATH)
        save_income_statement_snapshot(
            period["id"],
            period["period_start"],
            period["period_end"],
            DB_PATH,
        )
        closing_summary = generate_closing_entries(period["id"], DB_PATH)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Period review could not be completed: {error}",
        ) from error

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE accounting_periods
            SET status = 'trial_balance_confirmed',
                reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                review_confirmed_at = COALESCE(review_confirmed_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (period["id"],),
        )
        row = get_period_row_by_id(conn, period["id"])

    result = format_period(row)
    result["postedEntries"] = post_summary.posted
    result["postingSkipped"] = post_summary.skipped
    result["totalProposals"] = post_summary.total_proposals
    result["generatedClosingEntries"] = closing_summary["generatedEntries"]
    return result


@app.post("/api/periods/current/confirm-trial-balance")
def confirm_current_trial_balance() -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_current_period_row(conn)

    ensure_period_is_ready_to_finalize(period)

    try:
        post_summary = post_approved_proposals(period["id"], DB_PATH)
        save_income_statement_snapshot(
            period["id"],
            period["period_start"],
            period["period_end"],
            DB_PATH,
        )
        closing_summary = generate_closing_entries(period["id"], DB_PATH)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Period review could not be completed: {error}",
        ) from error

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE accounting_periods
            SET status = 'trial_balance_confirmed',
                reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                review_confirmed_at = COALESCE(review_confirmed_at, CURRENT_TIMESTAMP)
            WHERE period_start = ?
              AND period_end = ?
            """,
            (
                CURRENT_PERIOD["period_start"],
                CURRENT_PERIOD["period_end"],
            ),
        )
        row = get_current_period_row(conn)

    result = format_period(row)
    result["postedEntries"] = post_summary.posted
    result["postingSkipped"] = post_summary.skipped
    result["totalProposals"] = post_summary.total_proposals
    result["generatedClosingEntries"] = closing_summary["generatedEntries"]
    return result


@app.get("/api/periods/current/closing-entries")
def get_current_period_closing_entries() -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_current_period_row(conn)

    closing_entry_ids = get_closing_entry_ids(period["id"], DB_PATH)

    with get_connection() as conn:
        closing_entries = get_proposed_journal_entries_response(
            conn,
            closing_entry_ids,
        )

    return {
        "period": format_period(period),
        "closingEntries": closing_entries,
    }


@app.get("/api/periods/{period_id}/closing-entries")
def get_period_closing_entries(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    closing_entry_ids = get_closing_entry_ids(period["id"], DB_PATH)

    with get_connection() as conn:
        closing_entries = get_proposed_journal_entries_response(
            conn,
            closing_entry_ids,
        )

    return {
        "period": format_period(period),
        "closingEntries": closing_entries,
    }


@app.post("/api/periods/current/closing-entries")
def generate_current_period_closing_entries() -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_current_period_row(conn)

    try:
        closing_summary = generate_closing_entries(period["id"], DB_PATH)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with get_connection() as conn:
        closing_entries = get_proposed_journal_entries_response(
            conn,
            closing_summary["generatedEntryIds"],
        )

    return {
        **closing_summary,
        "period": format_period(period),
        "closingEntries": closing_entries,
    }


@app.post("/api/periods/{period_id}/closing-entries")
def generate_period_closing_entries(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    try:
        closing_summary = generate_closing_entries(period["id"], DB_PATH)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with get_connection() as conn:
        closing_entries = get_proposed_journal_entries_response(
            conn,
            closing_summary["generatedEntryIds"],
        )

    return {
        **closing_summary,
        "period": format_period(period),
        "closingEntries": closing_entries,
    }


@app.post("/api/periods/current/confirm-closing-entries")
def confirm_current_period_closing_entries() -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_current_period_row(conn)

    try:
        post_summary = post_closing_entries(period["id"], DB_PATH)
        save_balance_sheet_snapshot(period["id"], period["period_end"], DB_PATH)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Closing entries could not be posted: {error}",
        ) from error

    with get_connection() as conn:
        row = get_current_period_row(conn)

    result = format_period(row)
    result["postedClosingEntries"] = post_summary.posted
    result["closingPostingSkipped"] = post_summary.skipped
    result["totalClosingProposals"] = post_summary.total_proposals
    return result


@app.post("/api/periods/{period_id}/confirm-closing-entries")
def confirm_period_closing_entries(period_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        period = get_period_row_by_id(conn, period_id)

    try:
        post_summary = post_closing_entries(period["id"], DB_PATH)
        save_balance_sheet_snapshot(period["id"], period["period_end"], DB_PATH)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Closing entries could not be posted: {error}",
        ) from error

    with get_connection() as conn:
        row = get_period_row_by_id(conn, period["id"])

    result = format_period(row)
    result["postedClosingEntries"] = post_summary.posted
    result["closingPostingSkipped"] = post_summary.skipped
    result["totalClosingProposals"] = post_summary.total_proposals
    return result


@app.get("/api/imports")
def get_imports() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.source,
                i.filename,
                i.row_count,
                i.imported_at,
                p.period_start,
                p.period_end,
                p.label AS period_label,
                COALESCE(et.stored_rows, st.stored_rows, 0) AS stored_rows,
                COALESCE(pje.proposed_rows, 0) AS proposed_rows
            FROM imports i
            LEFT JOIN accounting_periods p ON p.id = i.period_id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS stored_rows
                FROM etsy_transactions
                GROUP BY import_id
            ) et ON et.import_id = i.id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS stored_rows
                FROM staged_transactions
                GROUP BY import_id
            ) st ON st.import_id = i.id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS proposed_rows
                FROM proposed_journal_entries
                GROUP BY import_id
            ) pje ON pje.import_id = i.id
            ORDER BY i.imported_at DESC, i.id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "source": row["source"],
            "filename": row["filename"],
            "rowCount": row["row_count"],
            "storedRows": row["stored_rows"],
            "postedRows": row["proposed_rows"] or 0,
            "importedAt": row["imported_at"],
            "period": {
                "periodStart": row["period_start"],
                "periodEnd": row["period_end"],
                "label": row["period_label"],
            }
            if row["period_start"]
            else None,
            "status": "proposed"
            if (row["proposed_rows"] or 0) == row["stored_rows"]
            else "imported",
        }
        for row in rows
    ]


@app.get("/api/periods/{period_id}/imports")
def get_period_imports(period_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        get_period_row_by_id(conn, period_id)
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.source,
                i.filename,
                i.row_count,
                i.imported_at,
                p.period_start,
                p.period_end,
                p.label AS period_label,
                COALESCE(et.stored_rows, st.stored_rows, 0) AS stored_rows,
                COALESCE(pje.proposed_rows, 0) AS proposed_rows
            FROM imports i
            LEFT JOIN accounting_periods p ON p.id = i.period_id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS stored_rows
                FROM etsy_transactions
                GROUP BY import_id
            ) et ON et.import_id = i.id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS stored_rows
                FROM staged_transactions
                GROUP BY import_id
            ) st ON st.import_id = i.id
            LEFT JOIN (
                SELECT import_id, COUNT(*) AS proposed_rows
                FROM proposed_journal_entries
                GROUP BY import_id
            ) pje ON pje.import_id = i.id
            WHERE i.period_id = ?
            ORDER BY i.imported_at DESC, i.id DESC
            """,
            (period_id,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "source": row["source"],
            "filename": row["filename"],
            "rowCount": row["row_count"],
            "storedRows": row["stored_rows"],
            "postedRows": row["proposed_rows"] or 0,
            "importedAt": row["imported_at"],
            "period": {
                "periodStart": row["period_start"],
                "periodEnd": row["period_end"],
                "label": row["period_label"],
            }
            if row["period_start"]
            else None,
            "status": "proposed"
            if (row["proposed_rows"] or 0) == row["stored_rows"]
            else "imported",
        }
        for row in rows
    ]


@app.delete("/api/imports/{import_id}")
def delete_import(import_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        import_row = conn.execute(
            """
            SELECT id, filename
            FROM imports
            WHERE id = ?
            """,
            (import_id,),
        ).fetchone()

        if import_row is None:
            raise HTTPException(status_code=404, detail="Import was not found.")

        posted_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM proposed_journal_entries
            WHERE import_id = ?
              AND posted_journal_entry_id IS NOT NULL
            """,
            (import_id,),
        ).fetchone()[0]

        if posted_count:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This CSV has already been posted to the permanent ledger. "
                    "Clear or reverse posted ledger entries before deleting it."
                ),
            )

        proposed_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT id
                FROM proposed_journal_entries
                WHERE import_id = ?
                """,
                (import_id,),
            ).fetchall()
        ]
        staged_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT id
                FROM staged_transactions
                WHERE import_id = ?
                """,
                (import_id,),
            ).fetchall()
        ]

        deleted_proposed_lines = delete_rows_by_parent_ids(
            conn,
            "proposed_journal_lines",
            "proposed_journal_entry_id",
            proposed_ids,
        )
        deleted_etsy_rows = conn.execute(
            """
            DELETE FROM etsy_transactions
            WHERE import_id = ?
            """,
            (import_id,),
        ).rowcount
        deleted_proposed_entries = delete_rows_by_ids(
            conn,
            "proposed_journal_entries",
            proposed_ids,
        )
        deleted_staged_rows = delete_rows_by_ids(
            conn,
            "staged_transactions",
            staged_ids,
        )
        deleted_imports = conn.execute(
            """
            DELETE FROM imports
            WHERE id = ?
            """,
            (import_id,),
        ).rowcount

    return {
        "id": import_id,
        "filename": import_row["filename"],
        "deletedImports": deleted_imports,
        "deletedStagedRows": deleted_staged_rows,
        "deletedEtsyRows": deleted_etsy_rows,
        "deletedProposedEntries": deleted_proposed_entries,
        "deletedProposedLines": deleted_proposed_lines,
    }


@app.get("/api/accounts")
def get_accounts() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                code,
                name,
                account_type,
                normal_balance
            FROM accounts
            WHERE is_active = 1
            ORDER BY code
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "accountType": row["account_type"],
            "normalBalance": row["normal_balance"],
        }
        for row in rows
    ]


@app.post("/api/agent/chat")
def chat_with_accounting_agent(request: AgentChatRequest) -> AgentChatResponse:
    try:
        return run_agent_chat(request, DB_PATH)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/generate-csv/variable-costs")
async def generate_variable_cost_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    if not VARIABLE_COST_CSV_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="The variable cost estimate file is missing on the backend.",
        )

    try:
        monthly_rows = build_monthly_variable_cost_transaction_rows_from_content(
            contents,
            VARIABLE_COST_CSV_PATH,
        )
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file could not be decoded as text.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"The variable-cost CSV could not be generated: {error}",
        ) from error

    files = [
        {
            "monthKey": month_key,
            "monthLabel": format_month_label(month_key),
            "filename": build_variable_cost_output_filename(filename, month_key),
            "rowCount": len(rows),
            "csvText": serialize_transaction_csv(rows),
        }
        for month_key, rows in monthly_rows.items()
        if rows
    ]

    return {
        "sourceFilename": filename,
        "fileCount": len(files),
        "totalRows": sum(file["rowCount"] for file in files),
        "files": files,
    }


@app.post("/api/imports/etsy")
async def upload_etsy_import(
    file: UploadFile = File(...),
    month: str | None = Form(default=None),
    year: int | None = Form(default=None),
) -> dict[str, Any]:
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    try:
        with get_connection() as conn:
            period = get_or_create_import_period(conn, month, year)

        summary = import_etsy_csv_content(contents, filename, DB_PATH, period["id"])
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file could not be decoded as text.",
        ) from error
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"The uploaded CSV file could not be parsed: {error}",
        ) from error

    try:
        proposal_summary = propose_etsy_transactions(DB_PATH, period["id"])
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"The CSV was imported, but proposed journal entries could not be created: {error}",
        ) from error

    return {
        "filename": filename,
        "contentType": file.content_type,
        "sizeBytes": len(contents),
        "imported": summary.imported,
        "skipped": summary.skipped,
        "totalRows": summary.total_rows,
        "posted": proposal_summary.proposed,
        "postingSkipped": proposal_summary.skipped,
        "totalUnposted": proposal_summary.total_unproposed,
        "proposed": proposal_summary.proposed,
        "proposalSkipped": proposal_summary.skipped,
        "totalUnproposed": proposal_summary.total_unproposed,
        "period": format_period(period),
        "status": "proposed",
    }


@app.post("/api/periods/{period_id}/imports/etsy")
async def upload_period_etsy_import(
    period_id: int,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    try:
        with get_connection() as conn:
            ensure_accounting_period(conn)
            period = get_period_row_by_id(conn, period_id)

        summary = import_etsy_csv_content(contents, filename, DB_PATH, period["id"])
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file could not be decoded as text.",
        ) from error
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"The uploaded CSV file could not be parsed: {error}",
        ) from error

    try:
        proposal_summary = propose_etsy_transactions(DB_PATH, period["id"])
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"The CSV was imported, but proposed journal entries could not be created: {error}",
        ) from error

    return {
        "filename": filename,
        "contentType": file.content_type,
        "sizeBytes": len(contents),
        "imported": summary.imported,
        "skipped": summary.skipped,
        "totalRows": summary.total_rows,
        "posted": proposal_summary.proposed,
        "postingSkipped": proposal_summary.skipped,
        "totalUnposted": proposal_summary.total_unproposed,
        "proposed": proposal_summary.proposed,
        "proposalSkipped": proposal_summary.skipped,
        "totalUnproposed": proposal_summary.total_unproposed,
        "period": format_period(period),
        "status": "proposed",
    }


@app.post("/api/periods/{period_id}/imports/transactions")
async def upload_period_transaction_import(
    period_id: int,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()

    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    try:
        with get_connection() as conn:
            ensure_accounting_period(conn)
            period = get_period_row_by_id(conn, period_id)

        summary = import_transaction_csv_content(
            contents,
            filename,
            DB_PATH,
            period["id"],
        )
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file could not be decoded as text.",
        ) from error
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"The transaction CSV file could not be parsed: {error}",
        ) from error

    return {
        "filename": filename,
        "contentType": file.content_type,
        "sizeBytes": len(contents),
        "imported": summary.imported,
        "skipped": summary.skipped,
        "totalRows": summary.total_rows,
        "posted": summary.imported,
        "postingSkipped": summary.skipped,
        "totalUnposted": summary.total_rows,
        "proposed": summary.imported,
        "proposalSkipped": summary.skipped,
        "totalUnproposed": summary.total_rows,
        "period": format_period(period),
        "status": "proposed",
    }


@app.get("/api/transactions/etsy")
def get_etsy_transactions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                transaction_date,
                type,
                title,
                info,
                currency,
                amount,
                fees_taxes,
                net,
                tax_details,
                proposed_journal_entry_id,
                posted_at,
                journal_entry_id
            FROM etsy_transactions
            ORDER BY transaction_date DESC, id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "date": row["transaction_date"],
            "type": row["type"],
            "title": row["title"],
            "info": row["info"],
            "currency": row["currency"],
            "amount": row["amount"],
            "feesTaxes": row["fees_taxes"],
            "net": row["net"],
            "taxDetails": row["tax_details"],
            "posted": row["proposed_journal_entry_id"] is not None
            or row["posted_at"] is not None,
            "journalEntryId": row["proposed_journal_entry_id"]
            or row["journal_entry_id"],
        }
        for row in rows
    ]


@app.get("/api/periods/{period_id}/transactions/etsy")
def get_period_etsy_transactions(period_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        get_period_row_by_id(conn, period_id)
        rows = conn.execute(
            """
            SELECT
                id,
                transaction_date,
                type,
                title,
                info,
                currency,
                amount,
                fees_taxes,
                net,
                tax_details,
                proposed_journal_entry_id,
                posted_at,
                journal_entry_id
            FROM etsy_transactions
            WHERE period_id = ?
            ORDER BY transaction_date DESC, id DESC
            """,
            (period_id,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "date": row["transaction_date"],
            "type": row["type"],
            "title": row["title"],
            "info": row["info"],
            "currency": row["currency"],
            "amount": row["amount"],
            "feesTaxes": row["fees_taxes"],
            "net": row["net"],
            "taxDetails": row["tax_details"],
            "posted": row["proposed_journal_entry_id"] is not None
            or row["posted_at"] is not None,
            "journalEntryId": row["proposed_journal_entry_id"]
            or row["journal_entry_id"],
        }
        for row in rows
    ]


@app.get("/api/transactions/journal")
def get_journal_entries() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                pje.id AS journal_entry_id,
                pje.source_id,
                pje.entry_date,
                pje.source,
                pje.memo AS entry_memo,
                pje.status,
                pje.review_note,
                pje.flagged_reason,
                pjl.debit,
                pjl.credit,
                pjl.memo AS line_memo,
                a.code AS account_code,
                a.name AS account_name
            FROM proposed_journal_entries pje
            JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
            JOIN accounts a ON a.id = pjl.account_id
            WHERE pje.voided_at IS NULL
              AND pje.status != 'voided'
            ORDER BY pje.entry_date DESC, pje.id DESC, pjl.id
            """
        ).fetchall()

    return format_journal_entry_rows(rows)


@app.get("/api/periods/{period_id}/transactions/journal")
def get_period_journal_entries(period_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        ensure_accounting_period(conn)
        get_period_row_by_id(conn, period_id)
        rows = conn.execute(
            """
            SELECT
                pje.id AS journal_entry_id,
                pje.source_id,
                pje.entry_date,
                pje.source,
                pje.memo AS entry_memo,
                pje.status,
                pje.review_note,
                pje.flagged_reason,
                pjl.debit,
                pjl.credit,
                pjl.memo AS line_memo,
                a.code AS account_code,
                a.name AS account_name
            FROM proposed_journal_entries pje
            JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
            JOIN accounts a ON a.id = pjl.account_id
            WHERE pje.period_id = ?
              AND pje.voided_at IS NULL
              AND pje.status != 'voided'
            ORDER BY pje.entry_date DESC, pje.id DESC, pjl.id
            """,
            (period_id,),
        ).fetchall()

    return format_journal_entry_rows(rows)


@app.get("/api/ledger")
def get_permanent_ledger() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                je.id AS journal_entry_id,
                je.source_id,
                je.entry_date,
                je.source,
                je.memo AS entry_memo,
                je.status,
                je.posted_at,
                COALESCE(ap.label, 'Unassigned period') AS period_label,
                ap.period_start,
                ap.period_end,
                jl.debit,
                jl.credit,
                jl.memo AS line_memo,
                a.code AS account_code,
                a.name AS account_name
            FROM journal_entries je
            JOIN journal_lines jl ON jl.journal_entry_id = je.id
            JOIN accounts a ON a.id = jl.account_id
            LEFT JOIN accounting_periods ap ON ap.id = je.period_id
            WHERE je.status = 'posted'
            ORDER BY
                COALESCE(ap.period_start, je.entry_date) DESC,
                je.entry_date DESC,
                je.id DESC,
                jl.id
            """
        ).fetchall()

    entries = format_ledger_entry_rows(rows)
    grouped_periods: dict[str, dict[str, Any]] = {}

    for entry in entries:
        period_key = entry["periodStart"] or "unassigned"
        period = grouped_periods.setdefault(
            period_key,
            {
                "label": entry["periodLabel"],
                "periodStart": entry["periodStart"],
                "periodEnd": entry["periodEnd"],
                "entries": [],
            },
        )
        period["entries"].append(entry)

    return list(grouped_periods.values())


def get_proposed_journal_entry_response(
    conn: sqlite3.Connection,
    proposed_journal_entry_id: int,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
            pje.id AS journal_entry_id,
            pje.source_id,
            pje.entry_date,
            pje.source,
            pje.memo AS entry_memo,
            pje.status,
            pje.review_note,
            pje.flagged_reason,
            pjl.debit,
            pjl.credit,
            pjl.memo AS line_memo,
            a.code AS account_code,
            a.name AS account_name
        FROM proposed_journal_entries pje
        JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
        JOIN accounts a ON a.id = pjl.account_id
        WHERE pje.id = ?
        ORDER BY pjl.id
        """,
        (proposed_journal_entry_id,),
    ).fetchall()

    entries = format_journal_entry_rows(rows)

    if not entries:
        raise HTTPException(
            status_code=404,
            detail="Proposed journal entry was not found.",
        )

    return entries[0]


def get_proposed_journal_entries_response(
    conn: sqlite3.Connection,
    proposed_journal_entry_ids: list[int],
) -> list[dict[str, Any]]:
    if not proposed_journal_entry_ids:
        return []

    placeholders = ", ".join("?" for _ in proposed_journal_entry_ids)
    rows = conn.execute(
        f"""
        SELECT
            pje.id AS journal_entry_id,
            pje.source_id,
            pje.entry_date,
            pje.source,
            pje.memo AS entry_memo,
            pje.status,
            pje.review_note,
            pje.flagged_reason,
            pjl.debit,
            pjl.credit,
            pjl.memo AS line_memo,
            a.code AS account_code,
            a.name AS account_name
        FROM proposed_journal_entries pje
        JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
        JOIN accounts a ON a.id = pjl.account_id
        WHERE pje.id IN ({placeholders})
        ORDER BY pje.id, pjl.id
        """,
        proposed_journal_entry_ids,
    ).fetchall()

    return format_journal_entry_rows(rows)


def format_journal_entry_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped_entries: dict[int, dict[str, Any]] = {}

    for row in rows:
        entry_id = row["journal_entry_id"]
        entry = grouped_entries.setdefault(
            entry_id,
            {
                "id": entry_id,
                "etsyId": row["source_id"] if row["source"] == "etsy" else None,
                "date": row["entry_date"],
                "memo": row["entry_memo"],
                "source": row["source"],
                "debits": [],
                "credits": [],
                "amount": 0,
                "status": row["status"],
                "reviewNote": row["review_note"],
                "flaggedReason": row["flagged_reason"],
                "isFlagged": row["flagged_reason"] is not None,
            },
        )

        line = {
            "accountCode": row["account_code"],
            "accountName": row["account_name"],
            "amount": row["debit"] or row["credit"],
            "memo": row["line_memo"],
        }

        if row["debit"]:
            entry["debits"].append(line)
            entry["amount"] = round(entry["amount"] + row["debit"], 2)

        if row["credit"]:
            entry["credits"].append(line)

    return list(grouped_entries.values())


def format_ledger_entry_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped_entries: dict[int, dict[str, Any]] = {}

    for row in rows:
        entry_id = row["journal_entry_id"]
        entry = grouped_entries.setdefault(
            entry_id,
            {
                "id": entry_id,
                "etsyId": row["source_id"] if row["source"] == "etsy" else None,
                "date": row["entry_date"],
                "memo": row["entry_memo"],
                "source": row["source"],
                "amount": 0,
                "status": row["status"],
                "postedAt": row["posted_at"],
                "periodLabel": row["period_label"],
                "periodStart": row["period_start"],
                "periodEnd": row["period_end"],
                "debits": [],
                "credits": [],
            },
        )

        line = {
            "accountCode": row["account_code"],
            "accountName": row["account_name"],
            "amount": row["debit"] or row["credit"],
            "memo": row["line_memo"],
        }

        if row["debit"]:
            entry["debits"].append(line)
            entry["amount"] = round(entry["amount"] + row["debit"], 2)

        if row["credit"]:
            entry["credits"].append(line)

    return list(grouped_entries.values())


@app.post("/api/transactions/journal/manual")
def add_manual_proposed_journal_entry(
    request: ManualJournalEntryRequest,
) -> dict[str, Any]:
    if len(request.lines) < 2:
        raise HTTPException(
            status_code=400,
            detail="A journal entry needs at least two lines.",
        )

    validate_manual_journal_lines(request.lines)

    lines = [
        JournalLine(
            account_code=line.accountCode,
            debit=round(float(line.debit or 0), 2),
            credit=round(float(line.credit or 0), 2),
            memo=line.memo,
        )
        for line in request.lines
    ]

    try:
        with get_connection() as conn:
            ensure_accounting_period(conn)
            period = get_current_period_row(conn)

        proposed_journal_entry_id = create_manual_proposed_entry(
            period["id"],
            request.entryDate,
            request.memo,
            lines,
            DB_PATH,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with get_connection() as conn:
        return get_proposed_journal_entry_response(conn, proposed_journal_entry_id)


@app.post("/api/periods/{period_id}/transactions/journal/manual")
def add_period_manual_proposed_journal_entry(
    period_id: int,
    request: ManualJournalEntryRequest,
) -> dict[str, Any]:
    if len(request.lines) < 2:
        raise HTTPException(
            status_code=400,
            detail="A journal entry needs at least two lines.",
        )

    validate_manual_journal_lines(request.lines)

    lines = [
        JournalLine(
            account_code=line.accountCode,
            debit=round(float(line.debit or 0), 2),
            credit=round(float(line.credit or 0), 2),
            memo=line.memo,
        )
        for line in request.lines
    ]

    try:
        with get_connection() as conn:
            ensure_accounting_period(conn)
            period = get_period_row_by_id(conn, period_id)

        proposed_journal_entry_id = create_manual_proposed_entry(
            period["id"],
            request.entryDate,
            request.memo,
            lines,
            DB_PATH,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with get_connection() as conn:
        return get_proposed_journal_entry_response(conn, proposed_journal_entry_id)


@app.get("/api/transactions/journal/flagged")
def get_flagged_journal_entries() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                pje.id AS journal_entry_id,
                pje.source_id,
                pje.entry_date,
                pje.source,
                pje.memo AS entry_memo,
                pje.status,
                pje.review_note,
                pje.flagged_reason,
                pjl.debit,
                pjl.credit,
                pjl.memo AS line_memo,
                a.code AS account_code,
                a.name AS account_name
            FROM proposed_journal_entries pje
            JOIN proposed_journal_lines pjl ON pjl.proposed_journal_entry_id = pje.id
            JOIN accounts a ON a.id = pjl.account_id
            WHERE pje.flagged_reason IS NOT NULL
              AND pje.voided_at IS NULL
              AND pje.status != 'voided'
            ORDER BY pje.entry_date DESC, pje.id DESC, pjl.id
            """
        ).fetchall()

    return format_journal_entry_rows(rows)


@app.post("/api/transactions/journal/flag-suspicious")
def flag_suspicious_journal_entries() -> dict[str, Any]:
    flagged_ids = flag_uncategorized_proposals(DB_PATH)

    return {
        "flaggedCount": len(flagged_ids),
        "flaggedJournalEntryIds": flagged_ids,
    }


@app.post("/api/transactions/journal/{journal_entry_id}/void")
def void_proposed_journal_entry(
    journal_entry_id: int,
    request: VoidProposedEntryRequest,
) -> dict[str, Any]:
    voided = void_proposed_entry(
        journal_entry_id,
        request.reason,
        request.note,
        DB_PATH,
    )

    if not voided:
        raise HTTPException(
            status_code=404,
            detail="Proposed journal entry was not found or has already been posted.",
        )

    return {
        "id": journal_entry_id,
        "status": "voided",
    }


def validate_manual_journal_lines(lines: list[ManualJournalLineRequest]) -> None:
    for line in lines:
        debit = round(float(line.debit or 0), 2)
        credit = round(float(line.credit or 0), 2)

        if debit < 0 or credit < 0:
            raise HTTPException(
                status_code=400,
                detail="Journal entry lines cannot use negative amounts.",
            )

        if debit > 0 and credit > 0:
            raise HTTPException(
                status_code=400,
                detail="Each journal entry line can be either a debit or a credit, not both.",
            )

        if debit == 0 and credit == 0:
            raise HTTPException(
                status_code=400,
                detail="Each journal entry line needs a debit or credit amount.",
            )


def delete_rows_by_parent_ids(
    conn: sqlite3.Connection,
    table_name: str,
    parent_column: str,
    parent_ids: list[int],
) -> int:
    if not parent_ids:
        return 0

    placeholders = ", ".join("?" for _ in parent_ids)
    return conn.execute(
        f"""
        DELETE FROM {table_name}
        WHERE {parent_column} IN ({placeholders})
        """,
        parent_ids,
    ).rowcount


def delete_rows_by_ids(
    conn: sqlite3.Connection,
    table_name: str,
    row_ids: list[int],
) -> int:
    if not row_ids:
        return 0

    placeholders = ", ".join("?" for _ in row_ids)
    return conn.execute(
        f"""
        DELETE FROM {table_name}
        WHERE id IN ({placeholders})
        """,
        row_ids,
    ).rowcount


def ensure_accounting_period(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accounting_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            reviewed_at TEXT,
            adjusted_at TEXT,
            closed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "accounting_periods", "reviewed_at", "TEXT")
    ensure_column(conn, "accounting_periods", "adjusted_at", "TEXT")
    ensure_column(conn, "accounting_periods", "review_confirmed_at", "TEXT")
    ensure_column(conn, "accounting_periods", "statements_generated_at", "TEXT")
    ensure_column(conn, "accounting_periods", "closing_confirmed_at", "TEXT")
    ensure_column(conn, "accounting_periods", "closed_at", "TEXT")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounting_periods_dates
        ON accounting_periods(period_start, period_end)
        """
    )
    conn.execute(
        """
        INSERT INTO accounting_periods (
            period_start,
            period_end,
            label,
            status
        )
        VALUES (?, ?, ?, 'open')
        ON CONFLICT(period_start, period_end) DO NOTHING
        """,
        (
            CURRENT_PERIOD["period_start"],
            CURRENT_PERIOD["period_end"],
            CURRENT_PERIOD["label"],
        ),
    )


def get_or_create_import_period(
    conn: sqlite3.Connection,
    month: str | None,
    year: int | None,
) -> sqlite3.Row:
    ensure_accounting_period(conn)

    if month is None and year is None:
        return get_current_period_row(conn)

    if month is None or year is None:
        raise HTTPException(
            status_code=400,
            detail="Please provide both month and year for the accounting period.",
        )

    period = build_period_from_month_year(month, year)
    conn.execute(
        """
        INSERT INTO accounting_periods (
            period_start,
            period_end,
            label,
            status
        )
        VALUES (?, ?, ?, 'open')
        ON CONFLICT(period_start, period_end) DO NOTHING
        """,
        (
            period["period_start"],
            period["period_end"],
            period["label"],
        ),
    )

    return get_period_row_by_dates(
        conn,
        period["period_start"],
        period["period_end"],
    )


def build_period_from_month_year(month: str, year: int) -> dict[str, str]:
    normalized_month = month.strip().lower()

    if normalized_month.isdigit():
        month_number = int(normalized_month)
    else:
        month_number = MONTH_NAMES.get(normalized_month, 0)

    if month_number < 1 or month_number > 12:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid accounting month.",
        )

    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid accounting year.",
        )

    last_day = monthrange(year, month_number)[1]
    period_start = date(year, month_number, 1)
    period_end = date(year, month_number, last_day)
    label = f"{period_start.strftime('%B')} {year}"

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "label": label,
    }


def get_period_row_by_dates(
    conn: sqlite3.Connection,
    period_start: str,
    period_end: str,
) -> sqlite3.Row:
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
        WHERE period_start = ?
          AND period_end = ?
        LIMIT 1
        """,
        (
            period_start,
            period_end,
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError("Accounting period could not be created.")

    return row


def get_period_row_by_id(conn: sqlite3.Connection, period_id: int) -> sqlite3.Row:
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
        raise HTTPException(status_code=404, detail="Accounting period was not found.")

    return row


def get_latest_closed_period_row(conn: sqlite3.Connection) -> sqlite3.Row:
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
        WHERE status = 'closed'
           OR closed_at IS NOT NULL
        ORDER BY period_end DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No closed accounting period is available yet.",
        )

    return row


def get_current_period_row(conn: sqlite3.Connection) -> sqlite3.Row:
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
        WHERE period_start = ?
          AND period_end = ?
        LIMIT 1
        """,
        (
            CURRENT_PERIOD["period_start"],
            CURRENT_PERIOD["period_end"],
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError("Current accounting period could not be created.")

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


def ensure_period_is_ready_to_finalize(period: sqlite3.Row) -> None:
    period_end = date.fromisoformat(period["period_end"])
    first_safe_date = period_end + timedelta(days=MIN_FINALIZATION_DELAY_DAYS)

    if date.today() < first_safe_date:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{period['label']} should not be finalized yet. Etsy can delay "
                f"CSV rows for up to {MIN_FINALIZATION_DELAY_DAYS} days after "
                f"month end, so finalize this period on or after "
                f"{first_safe_date.isoformat()}."
            ),
        )


def build_variable_cost_output_filename(
    original_filename: str,
    month_key: str | None = None,
) -> str:
    stem = Path(original_filename or "etsy_sold_order_items").stem
    safe_stem = "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in stem
    ).strip("_")

    if not safe_stem:
        safe_stem = "etsy_sold_order_items"

    suffix = f"_{month_key.replace('-', '_')}" if month_key else ""
    return f"{safe_stem}{suffix}_variable_cost_transactions.csv"


def format_month_label(month_key: str) -> str:
    year, month = month_key.split("-")
    return f"{MONTH_NAMES_BY_NUMBER[int(month)]} {year}"


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
