from dataclasses import dataclass


@dataclass(frozen=True)
class EtsyTransaction:
    source_file: str
    source_row: int
    transaction_date: str
    type: str
    title: str
    info: str
    currency: str
    amount: float
    fees_taxes: float
    net: float
    tax_details: str


@dataclass(frozen=True)
class ImportSummary:
    imported: int
    skipped: int
    total_rows: int


@dataclass(frozen=True)
class JournalLine:
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    memo: str = ""


@dataclass(frozen=True)
class GeneratedTransactionRow:
    entry_date: str
    memo: str
    debit_account: str
    credit_account: str
    debit_amount: float
    credit_amount: float
    source: str
    source_id: str


@dataclass(frozen=True)
class PostingSummary:
    posted: int
    skipped: int
    total_unposted: int


@dataclass(frozen=True)
class ProposalSummary:
    proposed: int
    skipped: int
    total_unproposed: int


@dataclass(frozen=True)
class LedgerPostSummary:
    posted: int
    skipped: int
    total_proposals: int


class Account:
    pass
