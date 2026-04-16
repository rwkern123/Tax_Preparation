from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099NECData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1099_nec_text(text: str) -> Form1099NECData:
    data = Form1099NECData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Payer info — appears before PAYER'S TIN line
    payer_match = re.search(
        r"PAYER['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    # Payer TIN (EIN format XX-XXXXXXX)
    payer_tin_match = re.search(
        r"PAYER['\u2019]?S\s+TIN[^\d]{0,10}(\d{2}-\d{7}|\d{9}|\d{2}\s\d{7})",
        text,
        re.IGNORECASE,
    )
    if payer_tin_match:
        data.payer_tin = re.sub(r"\s", "", payer_tin_match.group(1))

    # Recipient TIN (SSN or EIN — may be masked to last 4)
    recipient_tin_match = re.search(
        r"RECIPIENT['\u2019]?S\s+TIN[^\d]{0,10}([\dX*]{3}-[\dX*]{2}-\d{4}|\d{2}-\d{7}|\*{5}\d{4})",
        text,
        re.IGNORECASE,
    )
    if recipient_tin_match:
        data.recipient_tin = recipient_tin_match.group(1).strip()

    # Recipient name
    recipient_match = re.search(
        r"RECIPIENT['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if recipient_match:
        data.recipient_name = recipient_match.group(1).strip()[:120]

    # Street address
    addr_match = re.search(
        r"Street\s+address[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if addr_match:
        data.recipient_street = addr_match.group(1).strip()[:120]

    # City/state/zip line
    city_match = re.search(
        r"City\s+or\s+town[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if city_match:
        data.recipient_city_state_zip = city_match.group(1).strip()[:120]

    # Account number
    acct_match = re.search(
        r"Account\s+number[^:\n]*[:\s]+([^\n]{1,40})", text, re.IGNORECASE
    )
    if acct_match:
        candidate = acct_match.group(1).strip()
        # Ignore if it looks like instruction boilerplate
        if not re.search(r"\(see\s+instructions\)", candidate, re.IGNORECASE):
            data.account_number = candidate[:40]

    # Box 1 — Nonemployee compensation (the primary field)
    data.box1_nonemployee_compensation = _money(
        r"(?:1\.?\s*)?Nonemployee\s+compensation", text
    )

    # Box 2 — Direct sales checkbox (presence of keyword is enough)
    data.box2_direct_sales = bool(
        re.search(r"direct\s+sales\s+totaling\s+\$?5,?000", text, re.IGNORECASE)
    )

    # Box 3 — Excess golden parachute payments
    data.box3_excess_golden_parachute = _money(
        r"(?:3\.?\s*)?(?:Excess\s+)?golden\s+parachute", text
    )

    # Box 4 — Federal income tax withheld
    data.box4_fed_withholding = _money(
        r"(?:4\.?\s*)?Federal\s+income\s+tax\s+withheld", text
    )

    # Box 5 — State tax withheld
    data.box5_state_tax_withheld = _money(
        r"(?:5\.?\s*)?State\s+tax\s+withheld", text
    )

    # Box 6 — State/Payer's state number (text, not a dollar amount)
    state_no_match = re.search(
        r"(?:6\.?\s*)?State\s*/\s*Payer['\u2019]?s\s+state\s+no\.?\s*([A-Z]{2}[^\n]{0,20})",
        text,
        re.IGNORECASE,
    )
    if state_no_match:
        data.box6_state_payer_no = state_no_match.group(1).strip()[:40]

    # Box 7 — State income
    data.box7_state_income = _money(r"(?:7\.?\s*)?State\s+income", text)

    # Corrected flag
    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence: score by populated fields (box1 is most important)
    fields = [
        data.payer_name,
        data.payer_tin,
        data.recipient_name,
        data.recipient_tin,
        data.box1_nonemployee_compensation,
        data.box4_fed_withholding,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    # Weight box1 heavily — it's the primary data point
    if data.box1_nonemployee_compensation is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 7), 2)

    return data
