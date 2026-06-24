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
class PostingSummary:
    posted: int
    skipped: int
    total_unposted: int

class Account:
    pass