from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099RData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text, require_decimal=True)


def parse_1099_r_text(text: str) -> Form1099RData:
    data = Form1099RData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Payer name
    payer_match = re.search(
        r"PAYER['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    # Payer TIN
    payer_tin_match = re.search(
        r"PAYER['\u2019]?S\s+(?:federal\s+)?TIN[^\d]{0,10}(\d{2}-\d{7}|\d{9}|\d{2}\s\d{7})",
        text,
        re.IGNORECASE,
    )
    if payer_tin_match:
        data.payer_tin = re.sub(r"\s", "", payer_tin_match.group(1))

    # Recipient TIN
    recipient_tin_match = re.search(
        r"RECIPIENT['\u2019]?S\s+(?:federal\s+)?TIN[^\d]{0,10}([\dX*]{3}-[\dX*]{2}-\d{4}|\d{2}-\d{7}|\*{5}\d{4})",
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

    # Account number
    acct_match = re.search(
        r"Account\s+number[^:\n]*[:\s]+([^\n]{1,40})", text, re.IGNORECASE
    )
    if acct_match:
        candidate = acct_match.group(1).strip()
        if not re.search(r"\(see\s+instructions\)|\$", candidate, re.IGNORECASE):
            data.account_number = candidate[:40]

    # Box 1 — Gross distribution
    data.box1_gross_distribution = _money(
        r"(?:1\.?\s*)?Gross\s+distribution", text
    )

    # Box 2a — Taxable amount
    data.box2a_taxable_amount = _money(
        r"(?:2a\.?\s*)?Taxable\s+amount", text
    )

    # Box 2b checkboxes — presence of keywords signals checked
    data.box2b_taxable_not_determined = bool(
        re.search(r"Taxable\s+amount\s+not\s+determined", text, re.IGNORECASE)
    )
    # "Total distribution" checkbox — only flag when it appears in the 2b context
    # (avoid false positive from instructions prose)
    data.box2b_total_distribution = bool(
        re.search(r"2b[^\n]{0,40}Total\s+distribution|Total\s+distribution[^\n]{0,40}2b", text, re.IGNORECASE)
    )

    # Box 3 — Capital gain (included in 2a)
    # Require the "3" prefix to avoid matching instructions prose ("capital gain on Form 4972")
    data.box3_capital_gain = _money(
        r"3\.?\s+Capital\s+gain", text
    )

    # Box 4 — Federal income tax withheld
    data.box4_fed_withholding = _money(
        r"(?:4\.?\s*)?Federal\s+income\s+tax\s+withheld", text
    )

    # Box 5 — Employee contributions / Roth / insurance premiums
    data.box5_employee_contributions = _money(
        r"(?:5\.?\s*)?Employee\s+contributions", text
    )

    # Box 7 — Distribution code(s)
    # The code is typically 1-2 chars: digit or letter
    code_match = re.search(
        r"(?:7\.?\s*)?Distribution\s+code[s]?[^:\n]{0,20}[:\s]+([1-9A-HJ-NP-Z]{1,2})",
        text,
        re.IGNORECASE,
    )
    if code_match:
        data.box7_distribution_code = code_match.group(1).strip().upper()

    # Box 7 IRA/SEP/SIMPLE checkbox
    data.box7_ira_sep_simple = bool(
        re.search(r"IRA\s*/\s*SEP\s*/\s*SIMPLE", text, re.IGNORECASE)
    )

    # Box 14 — State tax withheld
    data.box14_state_tax_withheld = _money(
        r"(?:14\.?\s*)?State\s+tax\s+withheld", text
    )

    # Box 15 — State/Payer's state no.
    state_no_match = re.search(
        r"(?:15\.?\s*)?State\s*/\s*Payer['\u2019]?s\s+state\s+no\.?\s*([A-Z]{2}[^\n]{0,20})",
        text,
        re.IGNORECASE,
    )
    if state_no_match:
        data.box15_state_payer_no = state_no_match.group(1).strip()[:40]

    # Box 16 — State distribution
    data.box16_state_distribution = _money(
        r"(?:16\.?\s*)?State\s+distribution", text
    )

    # Corrected flag
    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence: scored by populated key fields
    fields = [
        data.payer_name,
        data.payer_tin,
        data.recipient_name,
        data.recipient_tin,
        data.box1_gross_distribution,
        data.box2a_taxable_amount,
        data.box4_fed_withholding,
        data.box7_distribution_code,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    # Weight box1 heavily
    if data.box1_gross_distribution is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 9), 2)

    return data
