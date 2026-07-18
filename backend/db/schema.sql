DROP TABLE IF EXISTS balance_sheet_snapshot_lines;
DROP TABLE IF EXISTS balance_sheet_snapshots;
DROP TABLE IF EXISTS income_statement_snapshots;
DROP TABLE IF EXISTS closing_batches;
DROP TABLE IF EXISTS proposed_journal_lines;
DROP TABLE IF EXISTS proposed_journal_entries;
DROP TABLE IF EXISTS journal_lines;
DROP TABLE IF EXISTS journal_entries;
DROP TABLE IF EXISTS staged_transactions;
DROP TABLE IF EXISTS etsy_transactions;
DROP TABLE IF EXISTS manual_expenses;
DROP TABLE IF EXISTS imports;
DROP TABLE IF EXISTS accounting_periods;
DROP TABLE IF EXISTS accounts;

CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    normal_balance TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE accounting_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    reviewed_at TEXT,
    adjusted_at TEXT,
    review_confirmed_at TEXT,
    statements_generated_at TEXT,
    closing_confirmed_at TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_accounting_periods_dates
ON accounting_periods(period_start, period_end);

CREATE INDEX idx_accounting_periods_status
ON accounting_periods(status);

CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'etsy',
    filename TEXT NOT NULL,
    file_hash TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'imported',
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id)
);

CREATE UNIQUE INDEX idx_imports_source_file_hash
ON imports(source, file_hash)
WHERE file_hash IS NOT NULL;

CREATE INDEX idx_imports_period
ON imports(period_id);

CREATE INDEX idx_imports_status
ON imports(status);

CREATE TABLE staged_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
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
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id),
    FOREIGN KEY (import_id) REFERENCES imports(id)
);

CREATE INDEX idx_staged_transactions_period
ON staged_transactions(period_id);

CREATE INDEX idx_staged_transactions_import
ON staged_transactions(import_id);

CREATE INDEX idx_staged_transactions_review_status
ON staged_transactions(review_status);

CREATE TABLE etsy_transactions (
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
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id),
    FOREIGN KEY (import_id) REFERENCES imports(id),
    FOREIGN KEY (staged_transaction_id) REFERENCES staged_transactions(id),
    FOREIGN KEY (proposed_journal_entry_id) REFERENCES proposed_journal_entries(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);

CREATE UNIQUE INDEX idx_etsy_transactions_import_row
ON etsy_transactions(import_id, source_row)
WHERE import_id IS NOT NULL;

CREATE UNIQUE INDEX idx_etsy_transactions_source_file_row
ON etsy_transactions(source_file, source_row)
WHERE source_file IS NOT NULL;

CREATE INDEX idx_etsy_transactions_period
ON etsy_transactions(period_id);

CREATE INDEX idx_etsy_transactions_date
ON etsy_transactions(transaction_date);

CREATE INDEX idx_etsy_transactions_review_status
ON etsy_transactions(review_status);

CREATE TABLE proposed_journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id),
    FOREIGN KEY (import_id) REFERENCES imports(id),
    FOREIGN KEY (staged_transaction_id) REFERENCES staged_transactions(id),
    FOREIGN KEY (closing_batch_id) REFERENCES closing_batches(id),
    FOREIGN KEY (posted_journal_entry_id) REFERENCES journal_entries(id)
);

CREATE UNIQUE INDEX idx_proposed_journal_entries_source_record
ON proposed_journal_entries(source, source_table, source_id)
WHERE source_table IS NOT NULL
  AND source_id IS NOT NULL;

CREATE INDEX idx_proposed_journal_entries_period
ON proposed_journal_entries(period_id);

CREATE INDEX idx_proposed_journal_entries_status
ON proposed_journal_entries(status);

CREATE INDEX idx_proposed_journal_entries_type
ON proposed_journal_entries(entry_type);

CREATE TABLE proposed_journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_journal_entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    memo TEXT,
    FOREIGN KEY (proposed_journal_entry_id) REFERENCES proposed_journal_entries(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX idx_proposed_journal_lines_entry
ON proposed_journal_lines(proposed_journal_entry_id);

CREATE INDEX idx_proposed_journal_lines_account
ON proposed_journal_lines(account_id);

CREATE TABLE journal_entries (
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
    posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id),
    FOREIGN KEY (proposed_journal_entry_id) REFERENCES proposed_journal_entries(id),
    FOREIGN KEY (closing_batch_id) REFERENCES closing_batches(id)
);

CREATE UNIQUE INDEX idx_journal_entries_source_record
ON journal_entries(source, source_table, source_id)
WHERE source_table IS NOT NULL
  AND source_id IS NOT NULL;

CREATE INDEX idx_journal_entries_date
ON journal_entries(entry_date);

CREATE INDEX idx_journal_entries_period
ON journal_entries(period_id);

CREATE INDEX idx_journal_entries_type
ON journal_entries(entry_type);

CREATE TABLE journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    memo TEXT,
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX idx_journal_lines_entry
ON journal_lines(journal_entry_id);

CREATE INDEX idx_journal_lines_account
ON journal_lines(account_id);

CREATE TABLE closing_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    posted_at TEXT,
    notes TEXT,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id)
);

CREATE UNIQUE INDEX idx_closing_batches_period
ON closing_batches(period_id);

CREATE INDEX idx_closing_batches_status
ON closing_batches(status);

CREATE TABLE income_statement_snapshots (
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
);

CREATE UNIQUE INDEX idx_income_statement_snapshots_period
ON income_statement_snapshots(period_id);

CREATE TABLE balance_sheet_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    total_assets REAL NOT NULL DEFAULT 0,
    total_liabilities REAL NOT NULL DEFAULT 0,
    total_equity REAL NOT NULL DEFAULT 0,
    total_liabilities_and_equity REAL NOT NULL DEFAULT 0,
    is_balanced INTEGER NOT NULL DEFAULT 0,
    statement_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id)
);

CREATE UNIQUE INDEX idx_balance_sheet_snapshots_period
ON balance_sheet_snapshots(period_id);

CREATE INDEX idx_balance_sheet_snapshots_as_of_date
ON balance_sheet_snapshots(as_of_date);

CREATE TABLE balance_sheet_snapshot_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    account_code TEXT NOT NULL,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    section TEXT NOT NULL,
    normal_balance TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    line_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (snapshot_id) REFERENCES balance_sheet_snapshots(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE INDEX idx_balance_sheet_snapshot_lines_snapshot
ON balance_sheet_snapshot_lines(snapshot_id);

CREATE INDEX idx_balance_sheet_snapshot_lines_account
ON balance_sheet_snapshot_lines(account_id);

CREATE TABLE manual_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER,
    import_id INTEGER,
    staged_transaction_id INTEGER,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    vendor TEXT,
    amount REAL NOT NULL,
    related_order_id TEXT,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    review_note TEXT,
    flagged_reason TEXT,
    proposed_journal_entry_id INTEGER,
    posted_at TEXT,
    journal_entry_id INTEGER,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (period_id) REFERENCES accounting_periods(id),
    FOREIGN KEY (import_id) REFERENCES imports(id),
    FOREIGN KEY (staged_transaction_id) REFERENCES staged_transactions(id),
    FOREIGN KEY (proposed_journal_entry_id) REFERENCES proposed_journal_entries(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);

CREATE INDEX idx_manual_expenses_period
ON manual_expenses(period_id);

CREATE INDEX idx_manual_expenses_review_status
ON manual_expenses(review_status);
