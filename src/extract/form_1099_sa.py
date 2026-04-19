from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099SAData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1099_sa_text(text: str) -> Form1099SAData:
    data = Form1099SAData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Payer name (the HSA trustee / custodian)
    payer_match = re.search(
        r"(?:TRUSTEE['\u2019]?S?|PAYER['\u2019]?S?)\s+name[^:\n]*[:\s]+([^\n]+)",
        text, re.IGNORECASE,
    )
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    # Recipient TIN (SSN)
    recipient_tin_match = re.search(
        r"(?:ACCOUNT\s+HOLDER|RECIPIENT)['\u2019]?S?\s+(?:TIN|SSN)[^\d]{0,10}"
        r"([\dX*]{3}-[\dX*]{2}-\d{4}|\*{5}\d{4})",
        text, re.IGNORECASE,
    )
    if recipient_tin_match:
        data.recipient_tin = recipient_tin_match.group(1).strip()

    # Recipient / account holder name
    recipient_match = re.search(
        r"(?:ACCOUNT\s+HOLDER|RECIPIENT)['\u2019]?S?\s+name[^:\n]*[:\s]+([^\n]+)",
        text, re.IGNORECASE,
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

    # Box 2 — Earnings on excess contributions
    data.box2_earnings_on_excess = _money(
        r"(?:2\.?\s*)?Earnings\s+on\s+excess\s+contributions?", text
    )

    # Box 3 — Distribution code (single digit or letter)
    dist_code_match = re.search(
        r"(?:3\.?\s*)?Distribution\s+code[^\n]{0,30}([1-9A-Z])\b", text, re.IGNORECASE
    )
    if dist_code_match:
        data.box3_distribution_code = dist_code_match.group(1).upper()

    # Box 4 — FMV on date of death
    data.box4_fmv_on_date_of_death = _money(
        r"(?:4\.?\s*)?FMV\s+on\s+date\s+of\s+death", text
    )

    # Box 5 — Account type (HSA / Archer MSA / Medicare Advantage MSA)
    if re.search(r"Medicare\s+Advantage\s+MSA", text, re.IGNORECASE):
        data.box5_account_type = "Medicare Advantage MSA"
    elif re.search(r"Archer\s+MSA", text, re.IGNORECASE):
        data.box5_account_type = "Archer MSA"
    elif re.search(r"\bHSA\b|health\s+savings\s+account", text, re.IGNORECASE):
        data.box5_account_type = "HSA"

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence
    fields = [
        data.payer_name,
        data.recipient_name,
        data.recipient_tin,
        data.box1_gross_distribution,
        data.box3_distribution_code,
        data.box5_account_type,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    if data.box1_gross_distribution is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 7), 2)

    return data
