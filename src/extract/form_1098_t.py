from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Form1098TData


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def parse_1098_t_text(text: str) -> Form1098TData:
    data = Form1098TData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Filer (institution) name — appears before FILER'S TIN or as first block
    filer_match = re.search(
        r"FILER['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if filer_match:
        data.filer_name = filer_match.group(1).strip()[:120]

    # Filer TIN (EIN)
    filer_tin_match = re.search(
        r"FILER['\u2019]?S\s+(?:federal\s+)?TIN[^\d]{0,10}(\d{2}-\d{7}|\d{9}|\d{2}\s\d{7})",
        text, re.IGNORECASE,
    )
    if filer_tin_match:
        data.filer_tin = re.sub(r"\s", "", filer_tin_match.group(1))

    # Student TIN (SSN)
    student_tin_match = re.search(
        r"STUDENT['\u2019]?S\s+(?:social\s+security\s+)?(?:TIN|SSN|number)[^\d]{0,10}"
        r"([\dX*]{3}-[\dX*]{2}-\d{4}|\*{5}\d{4})",
        text, re.IGNORECASE,
    )
    if student_tin_match:
        data.student_tin = student_tin_match.group(1).strip()

    # Student name
    student_name_match = re.search(
        r"STUDENT['\u2019]?S\s+name[^:\n]*[:\s]+([^\n]+)", text, re.IGNORECASE
    )
    if student_name_match:
        data.student_name = student_name_match.group(1).strip()[:120]

    # Account number
    acct_match = re.search(
        r"Account\s+number[^:\n]*[:\s]+([^\n]{1,40})", text, re.IGNORECASE
    )
    if acct_match:
        candidate = acct_match.group(1).strip()
        if not re.search(r"\(see\s+instructions\)", candidate, re.IGNORECASE):
            data.account_number = candidate[:40]

    # Box 1 — Payments received for qualified tuition and related expenses
    data.box1_payments_received = _money(
        r"(?:1\.?\s*)?Payments\s+received\s+for\s+qualified\s+tuition", text
    )

    # Box 4 — Adjustments made for a prior year
    data.box4_adjustments_prior_year = _money(
        r"(?:4\.?\s*)?Adjustments?\s+(?:made\s+)?for\s+(?:a\s+)?prior\s+year", text
    )

    # Box 5 — Scholarships or grants
    data.box5_scholarships_grants = _money(
        r"(?:5\.?\s*)?Scholarships?\s+or\s+grants?", text
    )

    # Box 6 — Adjustments to scholarships or grants for a prior year
    data.box6_adjustments_scholarships = _money(
        r"(?:6\.?\s*)?Adjustments?\s+to\s+scholarships?", text
    )

    # Box 7 — Checked if amounts include amounts for an academic period beginning
    # January–March of the following year
    data.box7_prior_year_amount = bool(
        re.search(
            r"(?:7\.?\s*)?(?:includes?\s+amounts?\s+for|academic\s+period\s+beginning\s+jan)",
            text, re.IGNORECASE,
        )
    )

    # Box 8 — At least half-time student
    data.box8_half_time_student = bool(
        re.search(r"(?:8\.?\s*)?(?:at\s+least\s+)?half[-\s]time\s+student", text, re.IGNORECASE)
    )

    # Box 9 — Graduate student
    data.box9_graduate_student = bool(
        re.search(r"(?:9\.?\s*)?Graduate\s+student", text, re.IGNORECASE)
    )

    # Box 10 — Insurance contract reimbursements / refunds
    data.box10_insurance_reimbursements = _money(
        r"(?:10\.?\s*)?Insurance\s+(?:contract\s+)?reimbursements?", text
    )

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence
    fields = [
        data.filer_name,
        data.filer_tin,
        data.student_name,
        data.student_tin,
        data.box1_payments_received,
        data.box5_scholarships_grants,
    ]
    populated = sum(1 for f in fields if f not in (None, "", False))
    if data.box1_payments_received is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 7), 2)

    return data
