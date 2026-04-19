from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099GData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1099_g_text(text: str) -> Form1099GData:
    data = Form1099GData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    payer_match = re.search(
        r"PAYER['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if payer_match:
        data.payer_name = payer_match.group(1).strip()[:120]

    payer_tin_match = re.search(
        r"PAYER['\u2019]?S\s+(?:federal\s+)?TIN[^\d]{0,10}(\d{2}-\d{7}|\d{9}|\d{2}\s\d{7})",
        text, re.IGNORECASE,
    )
    if payer_tin_match:
        data.payer_tin = re.sub(r"\s", "", payer_tin_match.group(1))

    recipient_tin_match = re.search(
        r"RECIPIENT['\u2019]?S\s+TIN[^\d]{0,10}([\dX*]{3}-[\dX*]{2}-\d{4}|\d{2}-\d{7}|\*{5}\d{4})",
        text, re.IGNORECASE,
    )
    if recipient_tin_match:
        data.recipient_tin = recipient_tin_match.group(1).strip()

    recipient_match = re.search(
        r"RECIPIENT['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if recipient_match:
        data.recipient_name = recipient_match.group(1).strip()[:120]

    acct_match = re.search(
        r"Account\s+number[^:\n]*[:\s]+([^\n]{1,40})", text, re.IGNORECASE
    )
    if acct_match:
        candidate = acct_match.group(1).strip()
        if not re.search(r"\(see\s+instructions\)", candidate, re.IGNORECASE):
            data.account_number = candidate[:40]

    # Box 1 — Unemployment compensation
    data.box1_unemployment_compensation = _money(
        r"(?:1\.?\s*)?Unemployment\s+compensation", text
    )

    # Box 2 — State or local income tax refunds / credits / offsets
    data.box2_state_local_tax_refund = _money(
        r"(?:2\.?\s*)?State\s+or\s+local\s+income\s+tax\s+refunds?", text
    )

    # Box 4 — Federal income tax withheld
    data.box4_fed_withholding = _money(
        r"(?:4\.?\s*)?Federal\s+income\s+tax\s+withheld", text
    )

    # Box 5 — RTAA payments
    data.box5_rtaa_payments = _money(r"(?:5\.?\s*)?RTAA\s+payments?", text)

    # Box 6 — Taxable grants
    data.box6_taxable_grants = _money(r"(?:6\.?\s*)?Taxable\s+grants?", text)

    # Box 7 — Agriculture payments
    data.box7_agriculture_payments = _money(
        r"(?:7\.?\s*)?Agriculture\s+payments?", text
    )

    # Box 8 — Trade or business checkbox
    data.box8_trade_or_business = bool(
        re.search(r"trade\s+or\s+business", text, re.IGNORECASE)
    )

    # Box 9 — Market gain
    data.box9_market_gain = _money(r"(?:9\.?\s*)?Market\s+gain", text)

    # Box 10a — State abbreviation
    state_match = re.search(
        r"(?:10a\.?\s*)?State[^\n]{0,10}([A-Z]{2})\b", text, re.IGNORECASE
    )
    if state_match:
        data.box10a_state = state_match.group(1)

    # Box 10b — State identification number
    state_id_match = re.search(
        r"(?:10b\.?\s*)?State\s+(?:identification\s+)?(?:no|number)[^\d]{0,10}([\dA-Z-]{3,20})",
        text, re.IGNORECASE,
    )
    if state_id_match:
        data.box10b_state_id = state_id_match.group(1).strip()[:20]

    # Box 11 — State income tax withheld
    data.box11_state_income_tax_withheld = _money(
        r"(?:11\.?\s*)?State\s+income\s+tax\s+withheld", text
    )

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence
    fields = [
        data.payer_name,
        data.payer_tin,
        data.recipient_name,
        data.recipient_tin,
        data.box1_unemployment_compensation,
        data.box2_state_local_tax_refund,
        data.box4_fed_withholding,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    if data.box1_unemployment_compensation is not None or data.box2_state_local_tax_refund is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 8), 2)

    return data
