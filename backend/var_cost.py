import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from .models import GeneratedTransactionRow
except ImportError:
    from models import GeneratedTransactionRow


DEFAULT_CURRENCY = "USD"
TRANSACTION_CSV_HEADERS = [
    "entry_date",
    "memo",
    "debit_account",
    "credit_account",
    "debit_amount",
    "credit_amount",
    "source",
    "source_id",
]
MATERIALS_EXPENSE_ACCOUNT = "5300"
SUPPLIES_EXPENSE_ACCOUNT = "5400"
CASH_ACCOUNT = "1000"
VARIABLE_COST_SOURCE = "variable_cost"


@dataclass(frozen=True)
class VariableCost:
    product_type: str
    materials_cost: float
    supplies_cost: float
    total_cost: float


@dataclass(frozen=True)
class SoldOrderItem:
    sale_date: str
    item_name: str
    quantity: int
    transaction_id: str
    order_id: str
    variations: str
    currency: str


def build_variable_cost_transaction_rows(
    sold_order_items_csv: str | Path,
    variable_cost_csv: str | Path,
) -> list[GeneratedTransactionRow]:
    cost_table = read_variable_cost_table(variable_cost_csv)
    sold_items = read_sold_order_items(sold_order_items_csv)
    return build_variable_cost_transaction_rows_from_items(sold_items, cost_table)


def build_variable_cost_transaction_rows_from_content(
    sold_order_items_content: bytes,
    variable_cost_csv: str | Path,
) -> list[GeneratedTransactionRow]:
    cost_table = read_variable_cost_table(variable_cost_csv)
    sold_items = read_sold_order_items_content(sold_order_items_content)
    return build_variable_cost_transaction_rows_from_items(sold_items, cost_table)


def build_monthly_variable_cost_transaction_rows_from_content(
    sold_order_items_content: bytes,
    variable_cost_csv: str | Path,
) -> dict[str, list[GeneratedTransactionRow]]:
    cost_table = read_variable_cost_table(variable_cost_csv)
    sold_items = read_sold_order_items_content(sold_order_items_content)
    grouped_items = group_sold_items_by_month(sold_items)

    return {
        month_key: build_variable_cost_transaction_rows_from_items(items, cost_table)
        for month_key, items in sorted(grouped_items.items())
    }


def build_variable_cost_transaction_rows_from_items(
    sold_items: list[SoldOrderItem],
    cost_table: dict[str, VariableCost],
) -> list[GeneratedTransactionRow]:
    rows: list[GeneratedTransactionRow] = []

    for item in sold_items:
        product_type = classify_product_type(item.variations, item.item_name)
        cost = cost_table.get(product_type)

        if cost is None:
            raise ValueError(
                f"No variable cost found for product type '{product_type}' "
                f"from variations '{item.variations}'."
            )

        materials_cost = round(cost.materials_cost * item.quantity, 2)
        supplies_cost = round(cost.supplies_cost * item.quantity, 2)

        if materials_cost:
            rows.append(
                build_variable_cost_transaction_row(
                    item,
                    product_type,
                    "Materials",
                    MATERIALS_EXPENSE_ACCOUNT,
                    materials_cost,
                )
            )

        if supplies_cost:
            rows.append(
                build_variable_cost_transaction_row(
                    item,
                    product_type,
                    "Supplies",
                    SUPPLIES_EXPENSE_ACCOUNT,
                    supplies_cost,
                )
            )

    return rows


def group_sold_items_by_month(
    sold_items: list[SoldOrderItem],
) -> dict[str, list[SoldOrderItem]]:
    grouped_items: dict[str, list[SoldOrderItem]] = {}

    for item in sold_items:
        month_key = item.sale_date[:7]
        grouped_items.setdefault(month_key, []).append(item)

    return grouped_items


def build_variable_cost_transaction_row(
    item: SoldOrderItem,
    product_type: str,
    cost_label: str,
    debit_account: str,
    cost: float,
) -> GeneratedTransactionRow:
    amount = abs(round(cost, 2))
    memo = (
        f"{cost_label} Expense: {product_type} - Order #{item.order_id} - "
        f"{item.item_name}"
    )

    return GeneratedTransactionRow(
        entry_date=item.sale_date,
        memo=memo,
        debit_account=debit_account,
        credit_account=CASH_ACCOUNT,
        debit_amount=amount,
        credit_amount=amount,
        source=VARIABLE_COST_SOURCE,
        source_id=item.transaction_id,
    )


def write_variable_cost_transaction_csv(
    rows: list[GeneratedTransactionRow],
    output_csv: str | Path,
) -> None:
    Path(output_csv).write_text(
        serialize_transaction_csv(rows),
        encoding="utf-8",
    )


def serialize_transaction_csv(rows: list[GeneratedTransactionRow]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRANSACTION_CSV_HEADERS)
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                "entry_date": row.entry_date,
                "memo": row.memo,
                "debit_account": row.debit_account,
                "credit_account": row.credit_account,
                "debit_amount": format_transaction_amount(row.debit_amount),
                "credit_amount": format_transaction_amount(row.credit_amount),
                "source": row.source,
                "source_id": row.source_id,
            }
        )

    return output.getvalue()


def generate_variable_cost_transaction_csv(
    sold_order_items_csv: str | Path,
    variable_cost_csv: str | Path,
    output_csv: str | Path,
) -> list[GeneratedTransactionRow]:
    rows = build_variable_cost_transaction_rows(sold_order_items_csv, variable_cost_csv)
    write_variable_cost_transaction_csv(rows, output_csv)
    return rows


def read_variable_cost_table(variable_cost_csv: str | Path) -> dict[str, VariableCost]:
    rows = read_csv_rows(variable_cost_csv)

    if not rows:
        raise ValueError("Variable cost CSV is empty.")

    headers = rows[0]
    product_types = [normalize_product_type(header) for header in headers[1:]]
    cost_rows = {
        normalize_label(row[0]): row[1:]
        for row in rows[1:]
        if row and row[0].strip()
    }

    materials_values = get_cost_row(cost_rows, "total materials expense")
    supplies_values = get_cost_row(cost_rows, "supplies expense")
    total_values = get_cost_row(cost_rows, "total expense")

    cost_table: dict[str, VariableCost] = {}
    for index, product_type in enumerate(product_types):
        cost_table[product_type] = VariableCost(
            product_type=product_type,
            materials_cost=parse_money(get_column_value(materials_values, index)),
            supplies_cost=parse_money(get_column_value(supplies_values, index)),
            total_cost=parse_money(get_column_value(total_values, index)),
        )

    return cost_table


def read_sold_order_items(sold_order_items_csv: str | Path) -> list[SoldOrderItem]:
    with Path(sold_order_items_csv).open(newline="", encoding="utf-8-sig") as file:
        return read_sold_order_items_rows(file)


def read_sold_order_items_content(contents: bytes) -> list[SoldOrderItem]:
    text = contents.decode("utf-8-sig")
    file = io.StringIO(text, newline="")
    return read_sold_order_items_rows(file)


def read_sold_order_items_rows(file) -> list[SoldOrderItem]:
    reader = csv.DictReader(file)
    required_columns = {
        "Sale Date",
        "Item Name",
        "Quantity",
        "Transaction ID",
        "Order ID",
        "Variations",
    }
    missing_columns = required_columns - set(reader.fieldnames or [])
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Sold order items CSV is missing columns: {missing}")

    return [
        SoldOrderItem(
            sale_date=parse_etsy_order_date(row["Sale Date"]),
            item_name=row["Item Name"].strip(),
            quantity=parse_quantity(row["Quantity"]),
            transaction_id=row["Transaction ID"].strip(),
            order_id=row["Order ID"].strip(),
            variations=row["Variations"].strip(),
            currency=(row.get("Currency") or DEFAULT_CURRENCY).strip(),
        )
        for row in reader
    ]


def classify_product_type(variations: str, item_name: str = "") -> str:
    normalized = normalize_variation_text(f"{variations} {item_name}")

    if "digital download" in normalized or "digital" in normalized:
        return "Digital Download"

    size_match = re.search(r"(\d+)\s*x\s*(\d+)", normalized)
    if not size_match:
        raise ValueError(f"Could not identify poster size from variations: {variations}")

    size = f"{size_match.group(1)} x {size_match.group(2)}"

    if "unframed" in normalized:
        frame_type = "Unframed"
    elif "framed" in normalized:
        frame_type = "Framed"
    else:
        raise ValueError(
            f"Could not identify framed/unframed status from variations: {variations}"
        )

    return f"{size} {frame_type}"


def read_csv_rows(path: str | Path) -> list[list[str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        return list(csv.reader(file))


def get_cost_row(cost_rows: dict[str, list[str]], label: str) -> list[str]:
    try:
        return cost_rows[label]
    except KeyError as error:
        raise ValueError(f"Variable cost CSV is missing row '{label}'.") from error


def get_column_value(values: list[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def normalize_label(value: str) -> str:
    return value.strip().rstrip(":").lower()


def normalize_product_type(value: str) -> str:
    cleaned = value.strip().rstrip(":")
    cleaned = cleaned.replace("(", "").replace(")", "")
    return " ".join(cleaned.split())


def normalize_variation_text(value: str) -> str:
    return " ".join(value.strip().lower().replace(":", " ").split())


def parse_money(value: str) -> float:
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return 0.0

    return round(float(cleaned), 2)


def parse_quantity(value: str) -> int:
    try:
        quantity = int(float(value.strip() or "0"))
    except ValueError as error:
        raise ValueError(f"Invalid quantity: {value}") from error

    if quantity < 1:
        raise ValueError(f"Quantity must be at least 1: {value}")

    return quantity


def parse_etsy_order_date(value: str) -> str:
    cleaned = value.strip()
    for date_format in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            pass

    raise ValueError(f"Invalid Etsy sale date: {value}")


def format_transaction_amount(value: float) -> str:
    return f"{round(value, 2):.2f}"


if __name__ == "__main__":
    base_downloads = Path.home() / "Downloads" / "CSV Files"
    sold_items_path = base_downloads / "EtsySoldOrderItems2026-1.csv"
    cost_table_path = base_downloads / "Variable Non-Etsy Expense Estimate - Sheet1.csv"
    output_path = base_downloads / "generated_variable_cost_transactions.csv"

    generated_rows = generate_variable_cost_transaction_csv(
        sold_items_path,
        cost_table_path,
        output_path,
    )

    print(f"Generated {len(generated_rows)} transaction CSV rows.")
    print(f"Wrote {output_path}")
