from __future__ import annotations

import re
from typing import Optional

from src.models import Form1098Data


def _money(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_1098_text(text: str) -> Form1098Data:
    data = Form1098Data()

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    lender_match = re.search(r"(?:Lender|Recipient)\s*(?:name)?[:\s]+([^\n]+)", text, re.IGNORECASE)
    if lender_match:
        data.lender_name = lender_match.group(1).strip()[:120]

    payer_match = re.search(r"(?:Payer|Borrower)\s*(?:name)?[:\s]+([^\n]+)", text, re.IGNORECASE)
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    borrowers = re.findall(r"Borrower\s*(?:name)?[:\s]+([^\n]+)", text, re.IGNORECASE)
    data.borrower_names = [b.strip()[:120] for b in borrowers if b.strip()]

    data.mortgage_interest_received = _money(r"(?:1\.?\s*Mortgage\s+interest\s+received|Mortgage\s+interest\s+received)[^\d\-]*([\-]?[\d,]+(?:\.\d{2})?)", text)
    data.points_paid = _money(r"(?:6\.?\s*Points\s+paid\s+on\s+purchase\s+of\s+principal\s+residence|Points\s+paid)[^\d\-]*([\-]?[\d,]+(?:\.\d{2})?)", text)
    data.mortgage_insurance_premiums = _money(r"(?:5\.?\s*Mortgage\s+insurance\s+premiums|Mortgage\s+insurance\s+premiums)[^\d\-]*([\-]?[\d,]+(?:\.\d{2})?)", text)
    data.real_estate_taxes = _money(r"(?:10\.?\s*Other|Real\s+estate\s+taxes)[^\d\-]*([\-]?[\d,]+(?:\.\d{2})?)", text)
    data.mortgage_principal_outstanding = _money(r"(?:2\.?\s*Outstanding\s+mortgage\s+principal|Outstanding\s+mortgage\s+principal)[^\d\-]*([\-]?[\d,]+(?:\.\d{2})?)", text)

    populated = sum(
        1
        for value in [
            data.lender_name,
            data.payer_name,
            data.mortgage_interest_received,
            data.points_paid,
            data.mortgage_insurance_premiums,
            data.real_estate_taxes,
            data.mortgage_principal_outstanding,
        ]
        if value not in (None, "")
    )
    data.confidence = round(min(1.0, populated / 7 + 0.15), 2)
    return data
