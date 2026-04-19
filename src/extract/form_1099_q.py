from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099QData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1099_q_text(text: str) -> Form1099QData:
    data = Form1099QData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Trustee / payer name
    payer_match = re.search(
        r"(?:TRUSTEE|PAYER)['\u2019]?S?\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    # Recipient TIN
    recipient_tin_match = re.search(
        r"RECIPIENT['\u2019]?S?\s+(?:TIN|SSN)[^\d]{0,10}([\dX*]{3}-[\dX*]{2}-\d{4}|\*{5}\d{4})",
        text, re.IGNORECASE,
    )
    if recipient_tin_match:
        data.recipient_tin = recipient_tin_match.group(1).strip()

    # Recipient name
    recipient_match = re.search(
        r"RECIPIENT['\u2019]?S?\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if recipient_match:
        data.recipient_name = recipient_match.group(1).strip()[:120]

    # Account number
    acct_match = re.search(
        r"Account\s+number[^:\n]*[:\s]+([^\n]{1,40})", text, re.IGNORECASE
    )
    if acct_match:
        candidate = acct_match.group(1).strip()
        if not re.search(r"\(see\s+instructions\)", candidate, re.IGNORECASE):
            data.account_number = candidate[:40]

    # Box 1 — Gross distribution
    data.box1_gross_distribution = _money(
        r"(?:1\.?\s*)?Gross\s+distribution", text
    )

    # Box 2 — Earnings
    data.box2_earnings = _money(r"(?:2\.?\s*)?Earnings\b", text)

    # Box 3 — Basis
    data.box3_basis = _money(r"(?:3\.?\s*)?Basis\b", text)

    # Box 4 — Trustee-to-trustee transfer checkbox
    data.trustee_to_trustee = bool(
        re.search(r"trustee[-\s]to[-\s]trustee", text, re.IGNORECASE)
    )

    # Box 5 — Qualified tuition program (529) vs Coverdell ESA
    data.qualified_tuition_program = bool(
        re.search(r"qualified\s+tuition\s+program|section\s+529", text, re.IGNORECASE)
    )

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence
    fields = [
        data.payer_name,
        data.recipient_name,
        data.recipient_tin,
        data.box1_gross_distribution,
        data.box2_earnings,
        data.box3_basis,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    if data.box1_gross_distribution is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 7), 2)

    return data
