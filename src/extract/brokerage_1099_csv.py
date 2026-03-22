"""Parser for Schwab-style 1099 composite CSV exports.

The CSV has the following structure:
  Row 1:  Account, XXXX-X341
  Row 2:  Tax Year, 2025
  (blank)
  "Form 1099DIV",
  "Box","Description","Amount","Total","Details",
  ... box rows ...
  "Form 1099INT",
  ... box rows ...
  "Form 1099 B",
  header row (column names)
  ... trade rows ...
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import List, Optional, Tuple

from src.models import Brokerage1099Data, Brokerage1099Trade


def _parse_dollar(value: str) -> Optional[float]:
    """Convert a string like '$1,008.05' or '1008.05' to float. Returns None if blank."""
    v = value.strip().lstrip("$").replace(",", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_date_csv(raw: str) -> Optional[str]:
    """Convert MM/DD/YYYY to YYYY-MM-DD. Returns None for blank or 'Various'."""
    raw = raw.strip()
    if not raw or raw.lower() == "various":
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _box_value(rows: list[list[str]], box_label: str) -> Optional[float]:
    """Find a row whose first column matches box_label and return the first non-empty dollar value."""
    label = box_label.strip().lower()
    for row in rows:
        if not row:
            continue
        if row[0].strip().lower() == label:
            # Prefer "Total" column (index 3), fall back to "Amount" (index 2)
            total = row[3].strip() if len(row) > 3 else ""
            amount = row[2].strip() if len(row) > 2 else ""
            val = _parse_dollar(total) if total else _parse_dollar(amount)
            if val is not None:
                return val
    return None


def parse_brokerage_1099_csv(
    content: str,
    source_file: str = "",
    source_sha256: str = "",
) -> Tuple[Brokerage1099Data, List[Brokerage1099Trade]]:
    """Parse a Schwab 1099 composite CSV.

    Returns a (Brokerage1099Data, list[Brokerage1099Trade]) tuple.
    """
    reader = csv.reader(io.StringIO(content))
    all_rows = list(reader)

    # --- header: account number and tax year ---
    account_number: Optional[str] = None
    year: Optional[int] = None
    for row in all_rows[:5]:
        if len(row) >= 2:
            key = row[0].strip().lower()
            if key == "account":
                account_number = row[1].strip()
            elif key == "tax year":
                try:
                    year = int(row[1].strip())
                except ValueError:
                    pass

    # --- split into sections ---
    div_rows: list[list[str]] = []
    int_rows: list[list[str]] = []
    b_rows: list[list[str]] = []  # trade data rows (after the header line)

    current_section = None
    b_headers_remaining = 0  # Schwab 1099-B has two header rows to skip

    for row in all_rows:
        if not row:
            continue
        first = row[0].strip().lower()
        if first == "form 1099div":
            current_section = "div"
            b_headers_remaining = 0
            continue
        if first == "form 1099int":
            current_section = "int"
            b_headers_remaining = 0
            continue
        if first in ("form 1099 b", "form 1099b"):
            current_section = "b"
            b_headers_remaining = 2  # box-number row + description row
            continue

        if current_section == "div":
            div_rows.append(row)
        elif current_section == "int":
            int_rows.append(row)
        elif current_section == "b":
            if b_headers_remaining > 0:
                b_headers_remaining -= 1
                continue
            b_rows.append(row)

    # --- build Brokerage1099Data ---
    data = Brokerage1099Data()
    data.broker_name = "Charles Schwab & Co., Inc."
    data.account_number = account_number
    data.year = year
    data.extraction_source = "csv"

    data.div_ordinary = _box_value(div_rows, "1a")
    data.div_qualified = _box_value(div_rows, "1b")
    data.div_cap_gain_distributions = _box_value(div_rows, "2a")
    data.div_foreign_tax_paid = _box_value(div_rows, "7")
    data.div_section_199a = _box_value(div_rows, "5")

    data.int_interest_income = _box_value(int_rows, "1")
    data.int_us_treasury = _box_value(int_rows, "3")

    checkable = [
        data.div_ordinary, data.div_qualified, data.div_cap_gain_distributions,
        data.div_foreign_tax_paid, data.div_section_199a,
        data.int_interest_income, data.int_us_treasury,
    ]
    populated = sum(1 for v in checkable if v is not None)
    data.confidence = round(min(1.0, populated / max(len(checkable), 1)), 2)

    # --- build trades ---
    # CSV 1099-B columns (0-indexed, per Schwab format):
    # 0: Description of property
    # 1: Date acquired
    # 2: Date sold or disposed
    # 3: Proceeds
    # 4: Cost or other basis
    # 5: Accrued market discount
    # 6: Wash sale loss disallowed
    # 7: Short-Term / Long-term
    # 8: Form 8949 Code
    # 9: Check if proceeds from collectibles/QOF
    # 10: Federal income tax withheld
    # 11: Covered / Uncovered (noncovered security)
    # 12: Gross proceeds / Net proceeds

    trades: List[Brokerage1099Trade] = []
    for row in b_rows:
        if len(row) < 5:
            continue
        description = row[0].strip()
        if not description:
            continue

        date_acquired_raw = row[1].strip() if len(row) > 1 else ""
        date_sold_raw = row[2].strip() if len(row) > 2 else ""
        proceeds_raw = row[3].strip() if len(row) > 3 else ""
        cost_raw = row[4].strip() if len(row) > 4 else ""
        wash_raw = row[6].strip() if len(row) > 6 else ""
        term_raw = row[7].strip().lower() if len(row) > 7 else ""
        code_raw = row[8].strip() if len(row) > 8 else ""
        fed_tax_raw = row[10].strip() if len(row) > 10 else ""
        covered_raw = row[11].strip().lower() if len(row) > 11 else ""

        date_acquired = None if date_acquired_raw.lower() == "various" else _parse_date_csv(date_acquired_raw)
        date_sold = _parse_date_csv(date_sold_raw)

        if "long" in term_raw:
            holding_period = "long"
        elif "short" in term_raw:
            holding_period = "short"
        else:
            holding_period = "unknown"

        basis_reported = "noncovered" if "uncovered" in covered_raw else "covered"

        proceeds = _parse_dollar(proceeds_raw)
        cost = _parse_dollar(cost_raw)
        wash = _parse_dollar(wash_raw)

        realized: Optional[float] = None
        if proceeds is not None and cost is not None:
            realized = round(proceeds - cost + (wash or 0.0), 2)

        trade = Brokerage1099Trade(
            broker_name=data.broker_name,
            source_file=source_file,
            source_sha256=source_sha256,
            description=description,
            date_acquired=date_acquired,
            date_sold_or_disposed=date_sold,
            proceeds_gross=proceeds,
            cost_basis=cost,
            wash_sale_amount=wash if wash else None,
            federal_income_tax_withheld=_parse_dollar(fed_tax_raw),
            holding_period=holding_period,
            basis_reported_to_irs=basis_reported,
            adjustment_code=code_raw if code_raw else None,
            form_8949_box=code_raw,
            realized_gain_loss=realized,
            raw_trade_line=",".join(row),
        )
        trades.append(trade)

    return data, trades
