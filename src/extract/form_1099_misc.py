from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1099MISCData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1099_misc_text(text: str) -> Form1099MISCData:
    data = Form1099MISCData()
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

    # Box 1 — Rents
    data.box1_rents = _money(r"(?:1\.?\s*)?Rents\b", text)

    # Box 2 — Royalties
    data.box2_royalties = _money(r"(?:2\.?\s*)?Royalties\b", text)

    # Box 3 — Other income
    data.box3_other_income = _money(r"(?:3\.?\s*)?Other\s+income", text)

    # Box 4 — Federal income tax withheld
    data.box4_fed_withholding = _money(
        r"(?:4\.?\s*)?Federal\s+income\s+tax\s+withheld", text
    )

    # Box 5 — Fishing boat proceeds
    data.box5_fishing_boat_proceeds = _money(
        r"(?:5\.?\s*)?Fishing\s+boat\s+proceeds?", text
    )

    # Box 6 — Medical and health care payments
    data.box6_medical_payments = _money(
        r"(?:6\.?\s*)?Medical\s+(?:and\s+health\s+care\s+)?payments?", text
    )

    # Box 7 — Direct sales checkbox ($5,000 or more)
    data.box7_direct_sales = bool(
        re.search(r"direct\s+sales\s+(?:of|totaling).*?\$?5,?000", text, re.IGNORECASE)
    )

    # Box 8 — Substitute payments in lieu of dividends
    data.box8_substitute_payments = _money(
        r"(?:8\.?\s*)?Substitute\s+payments?", text
    )

    # Box 10 — Crop insurance proceeds
    data.box10_crop_insurance = _money(
        r"(?:10\.?\s*)?Crop\s+insurance\s+proceeds?", text
    )

    # Box 12 — Section 409A deferrals
    data.box12_section_409a_deferrals = _money(
        r"(?:12\.?\s*)?Section\s+409A\s+deferrals?", text
    )

    # Box 14 — Gross proceeds paid to an attorney
    data.box14_gross_proceeds_attorney = _money(
        r"(?:14\.?\s*)?Gross\s+proceeds\s+(?:paid\s+)?to\s+(?:an?\s+)?attorney", text
    )

    # Box 15 — Section 409A income
    data.box15_section_409a_income = _money(
        r"(?:15\.?\s*)?Section\s+409A\s+income", text
    )

    # Box 16 — State tax withheld
    data.box16_state_tax_withheld = _money(
        r"(?:16\.?\s*)?State\s+tax\s+withheld", text
    )

    # Box 17 — State / Payer's state no.
    state_no_match = re.search(
        r"(?:17\.?\s*)?State\s*/\s*Payer['\u2019]?s?\s+state\s+no\.?\s*([A-Z]{2}[^\n]{0,20})",
        text, re.IGNORECASE,
    )
    if state_no_match:
        data.box17_state_payer_no = state_no_match.group(1).strip()[:40]

    # Box 18 — State income
    data.box18_state_income = _money(r"(?:18\.?\s*)?State\s+income\b", text)

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence
    dollar_fields = [
        data.box1_rents,
        data.box2_royalties,
        data.box3_other_income,
        data.box4_fed_withholding,
        data.box14_gross_proceeds_attorney,
    ]
    id_fields = [data.payer_name, data.payer_tin, data.recipient_name, data.recipient_tin]
    populated = sum(1 for f in id_fields if f not in (None, "")) + sum(
        1 for f in dollar_fields if f is not None
    )
    data.confidence = round(min(1.0, populated / 9), 2)

    return data
