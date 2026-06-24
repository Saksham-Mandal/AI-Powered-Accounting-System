DROP TABLE IF EXISTS journal_lines;
DROP TABLE IF EXISTS journal_entries;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS manual_expenses;
DROP TABLE IF EXISTS etsy_transactions;
DROP TABLE IF EXISTS imports;

CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_imports_source_file_hash
ON imports(source, file_hash)
WHERE file_hash IS NOT NULL;

CREATE TABLE etsy_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id INTEGER,
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
    posted_at TEXT,
    journal_entry_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (import_id) REFERENCES imports(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id)
);

CREATE UNIQUE INDEX idx_etsy_transactions_import_row
ON etsy_transactions(import_id, source_row)
WHERE import_id IS NOT NULL;

CREATE UNIQUE INDEX idx_etsy_transactions_source_file_row
ON etsy_transactions(source_file, source_row)
WHERE source_file IS NOT NULL;

CREATE INDEX idx_etsy_transactions_date
ON etsy_transactions(transaction_date);

CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    normal_balance TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE journal_entries (
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

CREATE UNIQUE INDEX idx_journal_entries_source_record
ON journal_entries(source, source_table, source_id)
WHERE source_table IS NOT NULL
  AND source_id IS NOT NULL;

CREATE INDEX idx_journal_entries_date
ON journal_entries(entry_date);

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

CREATE TABLE manual_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    vendor TEXT,
    amount REAL NOT NULL,
    related_order_id TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
