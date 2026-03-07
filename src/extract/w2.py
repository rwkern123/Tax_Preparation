from __future__ import annotations

import logging
import re

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text, parse_amount_token
from src.models import W2Data

_log = logging.getLogger(__name__)

_NON_NEGATIVE_FIELDS = [
    "box1_wages", "box2_fed_withholding", "box3_ss_wages",
    "box4_ss_tax", "box5_medicare_wages", "box6_medicare_tax",
    "box16_state_wages", "box17_state_tax",
]

_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","IA","ID","IL","IN",
    "KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC","ND","NE","NH",
    "NJ","NM","NV","NY","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VA",
    "VT","WA","WI","WV","WY",
}


def _extract_box12(text: str) -> dict[str, float]:
    """Extract all box 12 code/value pairs from W2 text.

    Handles two common PDF layouts:

    WEBB style (code on its own line after the box-12 sub-box label):
        12a Code See inst. for box 12
        D 4686.12
        12b Code
        DD 9664.46

    Dayforce style (code and value inline after "Code" keyword):
        12a See instructions for box 12  12b
        Code D  10632.00  Code W  1419.84
        12c  12d
        Code DD  6618.00  Code
    """
    result: dict[str, float] = {}

    # Scope search to the box-12 block (between first "12a" and "14 Other" / "15 State").
    # This prevents false-positive matches from the instruction pages.
    scope_match = re.search(
        r"(12[a-d]\b[\s\S]*?)(?=\b14\s+Other\b|\b15\s+State\b|\Z)",
        text, re.IGNORECASE,
    )
    scope = scope_match.group(1) if scope_match else text

    # Pass A — Dayforce style: "Code DD  6618.00" (code and value on the same line)
    for m in re.finditer(
        r"\bCode\s+([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        scope, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    # Pass B — WEBB style: "12x Code [optional text]\n DD  9664.46"
    # The code letter(s) appear on the line immediately after the sub-box label.
    for m in re.finditer(
        r"12[a-d]\s+(?:Code|See\s+inst[^\n]*)[\s]*\n\s*([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        scope, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    # Pass C — legacy / test style: "12 D 6000.00" or "Box 12 D 6000.00"
    for m in re.finditer(
        r"(?:Box\s+)?12\s+([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        scope, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    return result


def parse_w2_text(text: str) -> W2Data:
    data = W2Data()
    text = normalize_extracted_text(text)

    # --- Year ---
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # --- EIN ---
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    if ein_match:
        data.employer_ein = ein_match.group(1)

    # --- Employer name ---
    # Real W2s: "c Employer's name, address, and ZIP code" then name on next line.
    employer_match = re.search(
        r"(?:c\s+)?Employer(?:'s)?\s+name[^\n]*\n\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if not employer_match:
        # Fallback: "Employer's name: ABC Corp" on same line (unit-test / simple format)
        employer_match = re.search(
            r"Employer(?:'s)?\s+name[^\n:]*:\s*(.+)",
            text, re.IGNORECASE,
        )
    if employer_match:
        data.employer_name = employer_match.group(1).strip()[:120]

    # --- Employee name ---
    # "e Employee's first name and initial   Last name   Suff." then name on next line.
    emp_match = re.search(
        r"e\s+Employee(?:'s)?\s+(?:first\s+name|name)[^\n]*\n\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if emp_match:
        name_raw = emp_match.group(1).strip()
        # Strip ZIP codes and trailing address noise that appears in the same row.
        name_raw = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", name_raw)
        data.employee_name = re.sub(r"\s{2,}", " ", name_raw).strip()[:80]

    # --- Wage / tax boxes 1–6 ---
    data.box1_wages = extract_amount_after_label(r"(?:Box\s*[1Il]|1\.?\s*Wages)", text)
    data.box2_fed_withholding = extract_amount_after_label(
        r"(?:2\.?\s*Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?|"
        r"Box\s*2\s+Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?)",
        text,
    )
    data.box3_ss_wages = extract_amount_after_label(r"(?:Box\s*3|3\.?\s*Social\s*security\s*wages)", text)
    data.box4_ss_tax = extract_amount_after_label(r"(?:Box\s*4|4\.?\s*Social\s*security\s*tax)", text)
    data.box5_medicare_wages = extract_amount_after_label(r"(?:Box\s*5|5\.?\s*Medicare\s*wages)", text)
    data.box6_medicare_tax = extract_amount_after_label(r"(?:Box\s*6|6\.?\s*Medicare\s*tax)", text)

    # --- Box 12 ---
    data.box12 = _extract_box12(text)

    # --- Box 13: Retirement plan checkbox ---
    # pdfplumber often splits the checkbox row across lines, so "Retirement" and
    # "plan" may be separated by other label text (e.g. "Third-party\nemployee").
    # Allow up to 30 chars between the two words, then up to 60 chars to the X.
    data.box13_retirement_plan = bool(
        re.search(r"Retirement[\s\S]{0,30}plan[\s\S]{0,60}?\bX\b", text, re.IGNORECASE)
    )

    # --- State boxes 15–17 ---
    data.box16_state_wages = extract_amount_after_label(r"(?:Box\s*16|16\.?\s*State\s*wages)", text)
    data.box17_state_tax = extract_amount_after_label(r"(?:Box\s*17|17\.?\s*State\s*income\s*tax)", text)

    # --- State abbreviations ---
    data.states = sorted({s for s in re.findall(r"\b([A-Z]{2})\b", text) if s in _US_STATES})

    # --- Discard impossible negative values (OCR parse errors) ---
    for field_name in _NON_NEGATIVE_FIELDS:
        val = getattr(data, field_name)
        if val is not None and val < 0:
            _log.warning("w2: negative value %s for %s — discarding (likely parse error)", val, field_name)
            setattr(data, field_name, None)

    # --- Confidence scoring (9 key fields) ---
    populated = sum(
        1 for v in [
            data.employer_name,
            data.employer_ein,
            data.employee_name,
            data.box1_wages,
            data.box2_fed_withholding,
            data.box3_ss_wages,
            data.box4_ss_tax,
            data.box5_medicare_wages,
            data.box6_medicare_tax,
        ]
        if v not in (None, "")
    )
    critical_bonus = 0.1 if data.box1_wages is not None else 0.0
    data.confidence = round(min(1.0, populated / 9 + critical_bonus), 2)
    return data
