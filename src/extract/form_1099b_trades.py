from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.extract.text_utils import normalize_extracted_text, parse_amount_token
from src.models import Brokerage1099Trade

_DATE_PATTERNS = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"]


@dataclass
class SectionContext:
    holding_period: str = "unknown"
    basis_reported_to_irs: str = "unknown"


@dataclass
class ParseDiagnostics:
    row_candidates: int = 0
    parsed_rows: int = 0


def _parse_date(raw: str) -> Optional[str]:
    token = raw.strip()
    for fmt in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(token, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _derive_holding_period(date_acquired: Optional[str], date_sold: Optional[str]) -> str:
    if not date_acquired or not date_sold:
        return "unknown"
    try:
        d1 = datetime.strptime(date_acquired, "%Y-%m-%d")
        d2 = datetime.strptime(date_sold, "%Y-%m-%d")
    except ValueError:
        return "unknown"
    return "short" if (d2 - d1).days <= 365 else "long"


def _form_8949_box(holding_period: str, basis_reported: str) -> str:
    if holding_period == "short":
        return {"covered": "A", "noncovered": "B"}.get(basis_reported, "C")
    if holding_period == "long":
        return {"covered": "D", "noncovered": "E"}.get(basis_reported, "F")
    return ""


def _context_from_line(line: str, context: SectionContext) -> None:
    low = line.lower()
    if "short-term" in low:
        context.holding_period = "short"
    elif "long-term" in low:
        context.holding_period = "long"

    if "basis" in low and "reported" in low:
        if "not reported" in low or "noncovered" in low:
            context.basis_reported_to_irs = "noncovered"
        else:
            context.basis_reported_to_irs = "covered"


def _is_probable_trade_row(line: str) -> bool:
    date_count = len(re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line))
    return date_count >= 2


def _extract_description_and_identifier(prefix: str) -> Tuple[str, Optional[str]]:
    description = prefix.strip(" -\t") or "UNKNOWN SECURITY"
    security_identifier = None

    # Prefer explicit ticker/CUSIP in parentheses; otherwise trailing all-caps token.
    ident_match = re.search(r"\(([A-Z]{1,6}|[A-Z0-9]{9})\)", description)
    if ident_match:
        security_identifier = ident_match.group(1)
    else:
        t = re.search(r"\b([A-Z]{1,5})$", description)
        if t:
            security_identifier = t.group(1)

    return description, security_identifier


def _extract_amounts_after_disposition_date(line: str, date_hits: List[re.Match[str]]) -> List[float]:
    # Ignore date/acquired numbers by only parsing tokens after disposition date.
    tail = line[date_hits[1].end() :]
    amount_hits = re.findall(r"\(?-?\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?\)?", tail)
    amounts = [parse_amount_token(a) for a in amount_hits]
    return [a for a in amounts if a is not None]


def _extract_trade_line(
    line: str,
    broker_name: Optional[str],
    source_file: str,
    source_sha256: str,
    source_page: Optional[int],
    context: SectionContext,
) -> Optional[Brokerage1099Trade]:
    date_hits = list(re.finditer(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line))
    if len(date_hits) < 2:
        return None

    amounts = _extract_amounts_after_disposition_date(line, date_hits)
    if len(amounts) < 2:
        return None

    first_date = _parse_date(date_hits[0].group(0))
    second_date = _parse_date(date_hits[1].group(0))

    description, security_identifier = _extract_description_and_identifier(line[: date_hits[0].start()])

    proceeds = amounts[0]
    cost_basis = amounts[1]
    wash_sale_amount = amounts[2] if len(amounts) >= 3 else 0.0
    adjustment_amount = -abs(wash_sale_amount) if wash_sale_amount else 0.0

    holding_period = context.holding_period
    if holding_period == "unknown":
        holding_period = _derive_holding_period(first_date, second_date)

    basis_reported = context.basis_reported_to_irs
    realized_gain_loss = (proceeds - cost_basis) + adjustment_amount

    return Brokerage1099Trade(
        broker_name=broker_name,
        source_file=source_file,
        source_sha256=source_sha256,
        source_page=source_page,
        description=description,
        security_identifier=security_identifier,
        date_acquired=first_date,
        date_sold_or_disposed=second_date,
        proceeds_gross=proceeds,
        cost_basis=cost_basis,
        wash_sale_code="W" if wash_sale_amount else None,
        wash_sale_amount=wash_sale_amount,
        federal_income_tax_withheld=0.0,
        holding_period=holding_period,
        basis_reported_to_irs=basis_reported,
        adjustment_code="W" if wash_sale_amount else None,
        adjustment_amount=adjustment_amount,
        realized_gain_loss=realized_gain_loss,
        form_8949_box=_form_8949_box(holding_period, basis_reported),
        raw_trade_line=line,
    )


def parse_1099b_trades_text(
    text: str,
    broker_name: Optional[str],
    source_file: str,
    source_sha256: str,
) -> List[Brokerage1099Trade]:
    normalized = normalize_extracted_text(text)
    rows = [r.strip() for r in normalized.splitlines() if r.strip()]
    context = SectionContext()
    diagnostics = ParseDiagnostics()
    trades: List[Brokerage1099Trade] = []

    for row in rows:
        _context_from_line(row, context)

        if not _is_probable_trade_row(row):
            continue

        diagnostics.row_candidates += 1
        trade = _extract_trade_line(
            row,
            broker_name=broker_name,
            source_file=source_file,
            source_sha256=source_sha256,
            source_page=None,
            context=context,
        )
        if trade:
            diagnostics.parsed_rows += 1
            trades.append(trade)

    return trades


def trade_to_tax_row(client_id: str, tax_year: int, t: Brokerage1099Trade) -> Dict[str, object]:
    out = asdict(t)
    out["client_id"] = client_id
    out["tax_year"] = tax_year
    out["account_id_suffix"] = None
    return out


def trade_to_analytics_row(client_id: str, tax_year: int, t: Brokerage1099Trade) -> Dict[str, object]:
    return {
        "client_id": client_id,
        "tax_year": tax_year,
        "broker_name": t.broker_name,
        "source_file": t.source_file,
        "description": t.description,
        "ticker": t.security_identifier,
        "date_sold_or_disposed": t.date_sold_or_disposed,
        "trade_year_month": (t.date_sold_or_disposed or "")[:7] if t.date_sold_or_disposed else None,
        "proceeds_gross": t.proceeds_gross,
        "cost_basis": t.cost_basis,
        "adjustment_amount": t.adjustment_amount,
        "wash_sale_amount": t.wash_sale_amount,
        "realized_gain_loss": t.realized_gain_loss,
        "net_proceeds": (t.proceeds_gross or 0.0) + (t.adjustment_amount or 0.0),
    }


def summarize_trade_reconciliation(
    trades: List[Brokerage1099Trade],
    stated_proceeds: Optional[float],
    stated_cost_basis: Optional[float],
    stated_wash_sales: Optional[float],
) -> Dict[str, Optional[float]]:
    parsed_proceeds = round(sum((t.proceeds_gross or 0.0) for t in trades), 2)
    parsed_cost_basis = round(sum((t.cost_basis or 0.0) for t in trades), 2)
    parsed_wash_sales = round(sum((t.wash_sale_amount or 0.0) for t in trades), 2)

    return {
        "trade_count": len(trades),
        "parsed_proceeds": parsed_proceeds,
        "stated_proceeds": stated_proceeds,
        "proceeds_delta": None if stated_proceeds is None else round(parsed_proceeds - stated_proceeds, 2),
        "parsed_cost_basis": parsed_cost_basis,
        "stated_cost_basis": stated_cost_basis,
        "cost_basis_delta": None if stated_cost_basis is None else round(parsed_cost_basis - stated_cost_basis, 2),
        "parsed_wash_sales": parsed_wash_sales,
        "stated_wash_sales": stated_wash_sales,
        "wash_sales_delta": None if stated_wash_sales is None else round(parsed_wash_sales - stated_wash_sales, 2),
    }


def build_trade_exceptions(
    trades: List[Brokerage1099Trade],
    reconciliation: Optional[Dict[str, Optional[float]]] = None,
) -> List[Dict[str, str]]:
    exceptions: List[Dict[str, str]] = []
    for t in trades:
        if not t.date_acquired or not t.date_sold_or_disposed:
            exceptions.append({"source_file": t.source_file or "", "description": t.description, "issue": "missing_dates"})
        if t.holding_period == "unknown":
            exceptions.append({"source_file": t.source_file or "", "description": t.description, "issue": "unknown_holding_period"})
        if t.proceeds_gross is None or t.cost_basis is None:
            exceptions.append({"source_file": t.source_file or "", "description": t.description, "issue": "missing_amounts"})

    if reconciliation:
        for delta_key in ["proceeds_delta", "cost_basis_delta", "wash_sales_delta"]:
            delta = reconciliation.get(delta_key)
            if delta is not None and abs(delta) > 1.0:
                exceptions.append({"source_file": "(statement)", "description": "subtotal_reconciliation", "issue": f"{delta_key}:{delta}"})

    return exceptions
