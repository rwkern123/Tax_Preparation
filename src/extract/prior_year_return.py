"""
Local regex parser for prior-year Form 1040 tax return PDFs.

Handles TurboTax-generated PDFs (text-selectable) for tax years 2020–2025.
Extracts key fields from the main 1040 form pages (page 1 and page 2).
Falls back gracefully when fields are blank (no income, zero values).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from src.extract.text_utils import normalize_extracted_text, parse_amount_token
from src.models import PriorYearReturnData

_log = logging.getLogger(__name__)

_FILING_STATUSES = {
    "single": "Single",
    "married filing jointly": "Married Filing Jointly",
    "married filing separately": "Married Filing Separately",
    "head of household": "Head of Household",
    "qualifying surviving spouse": "Qualifying Surviving Spouse",
    "qualifying widow": "Qualifying Surviving Spouse",
}

_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","IA","ID","IL","IN",
    "KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC","ND","NE","NH",
    "NJ","NM","NV","NY","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VA",
    "VT","WA","WI","WV","WY",
}

# Fields used for confidence scoring
_CONFIDENCE_FIELDS = [
    "taxpayer_name",
    "taxpayer_ssn",
    "line_11_agi",
    "line_15_taxable_income",
    "line_24_total_tax",
    "line_33_total_payments",
    "filing_status",
    "year",
]


def _extract_year(text: str) -> Optional[int]:
    """Extract tax year from 1040 header.

    Looks for 'Form 1040 <year>' pattern, which appears at the top of every
    TurboTax-printed 1040. Also accepts standalone year on its own line as a
    fallback (Dayforce-style layout).
    """
    # TurboTax PDF header: "mroF\n1040\n2024" (reversed "Form" due to PDF column order)
    m = re.search(r"(?:Form\s+)?1040\s*[\n\r]\s*(20\d{2})\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Same line: "Form 1040 (2024)" or "1040 2024"
    m = re.search(r"\b1040\b[^\n]{0,40}(20\d{2})\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Standalone year after "mroF" artifact
    m = re.search(r"mroF\s*\n\s*1040\s*\n\s*(20\d{2})\b", text)
    if m:
        return int(m.group(1))
    # Summary page: "2025\nFederal\nTax\nReturn\nSummary" or "2024 Federal Tax Return"
    m = re.search(r"\b(20\d{2})\s*\n?\s*Federal\s+Tax\s+Return", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_filing_status(text: str) -> Optional[str]:
    """Detect filing status from the 1040.

    TurboTax prints ALL checkbox options as printed text regardless of which is
    checked, so we cannot simply look for a keyword. Instead we use structural
    evidence to determine the actual selection:

    - Two distinct SSNs anywhere in the document → Married Filing Jointly.
    - Spouse SSN field explicitly filled on the 1040 header → MFJ.
    - "If you checked the MFS box, enter the name of your spouse: [name]" → MFS.
    - "Head of household" with a qualifying person name → HOH.
    - Otherwise we cannot determine from text alone → return None.
    """
    # Evidence 1: two distinct SSNs anywhere in the document → MFJ
    all_ssns = re.findall(r"\b\d{3}[\s\-]\d{2}[\s\-]\d{4}\b", text)
    normalized = {re.sub(r"[\s\-]", "", s) for s in all_ssns}
    if len(normalized) >= 2:
        return "Married Filing Jointly"

    # Evidence 2: spouse name/SSN on the 1040 header line → MFJ
    spouse_filled = re.search(
        r"joint\s+return[^\n]{0,80}\n\s*([A-Za-z][A-Za-z\s\-']{2,30})\s{2,}\d{3}[\s\-]\d{2}[\s\-]\d{4}",
        text, re.IGNORECASE,
    )
    if spouse_filled:
        return "Married Filing Jointly"

    # Evidence 3: MFS box checked → spouse name entered on that line
    mfs_m = re.search(
        r"MFS\s+box[^\n]{0,60}name[^\n]{0,20}:\s*([A-Za-z][A-Za-z\s]{2,30})",
        text, re.IGNORECASE,
    )
    if mfs_m:
        return "Married Filing Separately"

    # Evidence 4: Head of household with qualifying person
    hoh_m = re.search(
        r"Head\s+of\s+household[^\n]{0,80}child['']?s\s+name[^\n]{0,30}:\s*([A-Za-z][A-Za-z\s]{2,20})",
        text, re.IGNORECASE,
    )
    if hoh_m:
        return "Head of Household"

    # Cannot determine from text alone — the printed checkbox text provides no signal
    return None


def _extract_ssn(text: str, label: str) -> Optional[str]:
    """Extract SSN near a label (e.g. 'Your social security number').

    TurboTax PDFs print SSNs as '410 77 0238' (space-separated groups).
    Returns formatted as 'XXX-XX-XXXX'.
    """
    pattern = rf"{re.escape(label)}[^\n]{{0,60}}(\d{{3}}[\s\-]\d{{2}}[\s\-]\d{{4}})"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        raw = re.sub(r"[\s\-]", "", m.group(1))
        return f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"
    # Try same-line compact: after "Last name" header, SSN appears on same line
    # Pattern: name then spaces then SSN groups on same line
    alt = re.search(
        r"(?:social\s+security\s+number|SSN)[^\n]{0,10}(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
        text, re.IGNORECASE,
    )
    if alt:
        raw = re.sub(r"[\s\-]", "", alt.group(1))
        return f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"
    return None


def _extract_names_and_ssns(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (taxpayer_name, taxpayer_ssn, spouse_name, spouse_ssn).

    TurboTax 1040 layout:
        Your first name and middle initial  Last name  Your social security number
        Ryan                                Kern        410 77 0238
        If joint return, spouse's first name ...        Spouse's social security number
        Brittany                            Webb        034 80 5887
    """
    # -- Taxpayer --
    # The taxpayer line appears after the label row; extract first non-label text line.
    tp_name: Optional[str] = None
    tp_ssn: Optional[str] = None
    sp_name: Optional[str] = None
    sp_ssn: Optional[str] = None

    # Match taxpayer name + SSN on same line (TurboTax puts them on one line)
    tp_m = re.search(
        r"(?:Your\s+first\s+name[^\n]*Last\s+name[^\n]*\n\s*)"
        r"([A-Za-z][A-Za-z\s\.\-']{1,40}?)\s+(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
        text, re.IGNORECASE,
    )
    if tp_m:
        tp_name = tp_m.group(1).strip()
        raw = re.sub(r"[\s\-]", "", tp_m.group(2))
        tp_ssn = f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"
    else:
        # Fallback: name line then SSN on same line without the header prefix
        tp_m2 = re.search(
            r"\n([A-Za-z][A-Za-z\s\.\-']{2,30})\s{3,}(\d{3}[\s\-]\d{2}[\s\-]\d{4})\s*\n",
            text,
        )
        if tp_m2:
            tp_name = tp_m2.group(1).strip()
            raw = re.sub(r"[\s\-]", "", tp_m2.group(2))
            tp_ssn = f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"

    # Fallback: pdfplumber sometimes extracts columns separately — name label on
    # one line, name value on next, then SSN label, then SSN value.
    if tp_name is None:
        nm = re.search(
            r"Your\s+first\s+name[^\n]*\n\s*([A-Za-z][A-Za-z\s\.\-']{1,40}?)\s*\n",
            text, re.IGNORECASE,
        )
        if nm:
            tp_name = nm.group(1).strip()
    if tp_ssn is None:
        ssn_m = re.search(
            r"Your\s+social\s+security\s+number[^\n]{0,20}\n\s*(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
            text, re.IGNORECASE,
        )
        if ssn_m:
            raw = re.sub(r"[\s\-]", "", ssn_m.group(1))
            tp_ssn = f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"

    # -- Spouse (MFJ) --
    sp_m = re.search(
        r"(?:joint\s+return[^\n]*\n\s*)"
        r"([A-Za-z][A-Za-z\s\.\-']{1,40}?)\s+(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
        text, re.IGNORECASE,
    )
    if sp_m:
        sp_name = sp_m.group(1).strip()
        raw = re.sub(r"[\s\-]", "", sp_m.group(2))
        sp_ssn = f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"
    else:
        # Alternative: look for "Spouse's social security number" label then find value
        sp_ssn_m = re.search(
            r"Spouse['']s\s+social\s+security\s+number[^\n]{0,20}\n\s*([A-Za-z][^\n]{2,30}?)"
            r"\s+(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
            text, re.IGNORECASE,
        )
        if sp_ssn_m:
            sp_name = sp_ssn_m.group(1).strip()
            raw = re.sub(r"[\s\-]", "", sp_ssn_m.group(2))
            sp_ssn = f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"

    return tp_name, tp_ssn, sp_name, sp_ssn


def _extract_address(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (street, city, state, zip) from the 1040 address block.

    TurboTax layout:
        Home address (number and street). If you have a P.O. box, see instructions.
        6311 Woodbrook Ln
        City, town, or post office...   State   ZIP code
        Houston                         TX      770086253
    """
    # Pass A: "Home address" label then next non-empty line is the street.
    # TurboTax puts form instructions on the same line as the street address:
    #   "6311 Woodbrook Ln  Check here if you, or your"
    # We stop at two or more spaces (column separator) to trim the instruction.
    ha_m = re.search(
        r"Home\s+address[^\n]+\n\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if ha_m:
        raw_street = ha_m.group(1).strip()
        # Trim at first run of 3+ spaces (column boundary) or common instruction phrases
        street = re.split(r"\s{3,}|(?:Check here|Apt\.|P\.O\. box)", raw_street)[0].strip()
        # Only keep if it looks like a street address (starts with a digit)
        if not re.match(r"^\d", street):
            street = None
        # Now find the CSZ line (City  ST  ZIP)
        csz_text = text[ha_m.end(): ha_m.end() + 400]
        city, state, zip_ = _parse_city_state_zip(csz_text)
        return street or None, city, state, zip_

    return None, None, None, None


def _parse_city_state_zip(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Find City ST ZIP in a block of text, searching line by line."""
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        # TurboTax: "Houston TX 770086253" (no space in 9-digit ZIP)
        m = re.match(
            r"^([A-Za-z][A-Za-z .\-']{1,40}?)\s+([A-Z]{2})\s+(\d{5,9})\s*$",
            line,
        )
        if m and m.group(2) in _US_STATES:
            city = m.group(1).strip()
            state = m.group(2)
            raw_zip = m.group(3)
            zip_ = f"{raw_zip[:5]}-{raw_zip[5:]}" if len(raw_zip) == 9 else raw_zip
            return city, state, zip_
    return None, None, None


def _line(
    label_pattern: str,
    text: str,
    *,
    require_decimal: bool = False,
    stop_pattern: Optional[str] = None,
    multiline: bool = False,
) -> Optional[float]:
    """Extract a dollar amount from a Form 1040 line.

    TurboTax prints integer amounts with a trailing period on the 1040:
        "1a Total amount from Form(s) W-2 . . . . . 1a 244,366."

    The trailing-period format is key: it distinguishes "244,366." (an amount)
    from form references like "Form 8995" or line references like "line 26".

    Args:
        label_pattern: Regex pattern for the line label/number.
        require_decimal: If True, match "X,XXX.YY" summary-page style amounts.
        stop_pattern: If provided, truncate the matched content at this pattern
            (useful for two-per-line fields like 3a/3b).
        multiline: If True, search across up to 2 lines (for wrapped lines).
    """
    span = r"[\s\S]{0,400}" if multiline else r"[^\n]{0,300}"
    m = re.search(rf"{label_pattern}({span})", text, re.IGNORECASE)
    if not m:
        return None

    content = m.group(0)

    # Truncate at stop_pattern (prevents bleeding into adjacent fields on same line)
    if stop_pattern:
        stop_m = re.search(stop_pattern, content[len(m.group(0)) - len(m.group(1)):], re.IGNORECASE)
        if stop_m:
            content = content[: len(m.group(0)) - len(m.group(1)) + stop_m.start()]

    if require_decimal:
        # Summary-page style: "$305,575.00" — exactly two decimal places
        candidates = re.findall(r"\$\s*([\d,]+\.\d{2})", content)
        if not candidates:
            candidates = re.findall(r"([\d,]+\.\d{2})", content)
    else:
        # TurboTax 1040 style: integer amounts end with "." e.g. "244,366."
        # Require ≥3-digit number (rules out "1." "2." line-number artifacts).
        # Allow optional two-decimal suffix for hybrid PDFs.
        candidates = re.findall(r"(?<!\d)([\d,]{2,}\d\.\d{2}|[\d,]{2,}\d\.)", content)

    if not candidates:
        return None

    # Last candidate on the line = the actual IRS field value
    raw = candidates[-1].rstrip(".")
    return parse_amount_token(raw)


def _form_present(text: str, *patterns: str) -> bool:
    """Return True if any pattern matches in text (case-insensitive)."""
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _window_after(text: str, anchor_pattern: str, window: int = 3000) -> str:
    """Return the text slice starting at the anchor match up to window chars."""
    m = re.search(anchor_pattern, text, re.IGNORECASE)
    if not m:
        return ""
    return text[m.start(): m.start() + window]


def _extract_occupations(text: str, data: PriorYearReturnData) -> None:
    """Extract taxpayer and spouse occupations from 1040 header area."""
    def _parse_occupation(block: str) -> Optional[str]:
        """Try label+next-line, then label+same-line."""
        m = re.search(
            r"occupation[^\n]{0,10}\n\s*([A-Za-z][A-Za-z\s\-]{1,30})",
            block, re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
        # Same-line: "Occupation  Engineer" or "Occupation: Engineer"
        m2 = re.search(
            r"occupation[\s:]{1,5}([A-Za-z][A-Za-z\s\-]{1,30})",
            block, re.IGNORECASE,
        )
        if m2:
            val = m2.group(1).strip()
            # Exclude generic label words that bleed in from adjacent columns
            if val.lower() not in ("if a joint return", "spouse", "your"):
                return val
        return None

    occ_positions = [mo.start() for mo in re.finditer(r"occupation", text, re.IGNORECASE)]

    if occ_positions:
        data.taxpayer_occupation = _parse_occupation(text[occ_positions[0]: occ_positions[0] + 200])

    if len(occ_positions) >= 2:
        candidate = _parse_occupation(text[occ_positions[1]: occ_positions[1] + 200])
        if candidate and candidate != data.taxpayer_occupation:
            data.spouse_occupation = candidate


def _extract_dependents(text: str, data: PriorYearReturnData) -> None:
    """Extract dependents from the 1040 dependents table."""
    header_m = re.search(
        r"Dependents\s*\(?see\s+instructions\)?[^\n]{0,100}\n",
        text, re.IGNORECASE,
    )
    if not header_m:
        return
    # Search in a window after the header
    window = text[header_m.end(): header_m.end() + 2000]
    # Each dependent line contains an SSN-like pattern
    dep_pattern = re.compile(
        r"([A-Za-z][A-Za-z\s\.\-']{2,40}?)\s{2,}(\d{3}[\s\-]\d{2}[\s\-]\d{4})\s{2,}([A-Za-z\s]{2,20})",
        re.IGNORECASE,
    )
    for dep_m in dep_pattern.finditer(window):
        name = dep_m.group(1).strip()
        raw_ssn = re.sub(r"[\s\-]", "", dep_m.group(2))
        ssn = f"{raw_ssn[:3]}-{raw_ssn[3:5]}-{raw_ssn[5:]}"
        relationship = dep_m.group(3).strip()
        # Look for CTC/ODC eligibility in the surrounding context
        context_start = dep_m.end()
        context = window[context_start: context_start + 200]
        ctc_eligible = bool(re.search(r"child\s+tax\s+credit", context, re.IGNORECASE))
        odc_eligible = bool(re.search(r"credit\s+for\s+other\s+dependents", context, re.IGNORECASE))
        data.dependents.append({
            "name": name,
            "ssn": ssn,
            "relationship": relationship,
            "ctc_eligible": ctc_eligible,
            "odc_eligible": odc_eligible,
        })


def _extract_refund_applied_forward(text: str, data: PriorYearReturnData) -> None:
    """Extract line 36 — refund applied to next-year estimated tax."""
    m = re.search(
        r"36\s+Amount.*?applied.*?estimated\s+tax[^\n]{0,200}?\.\s+36\s+([\d,]+\.(?:\d{2})?)",
        text, re.IGNORECASE,
    )
    if m:
        data.refund_applied_forward = parse_amount_token(m.group(1).rstrip("."))
    else:
        data.refund_applied_forward = _line(
            r"36\s+Amount.*?estimated\s+tax", text
        )


def _extract_extension(text: str, data: PriorYearReturnData) -> None:
    """Detect Form 4868 extension indicator."""
    if re.search(r"\b4868\b", text):
        data.extension_filed = True


def _extract_schedule_1_adjustments(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule 1 additional adjustments."""
    window = _window_after(text, r"SCHEDULE\s+1\b|Schedule\s+1\s*\(Form\s+1040\)", window=5000)
    if not window:
        window = text  # Fall back to full text
    data.sched1_educator_expenses = _line(r"11\s+Educator\s+expenses", window)
    data.sched1_hsa_deduction = _line(r"13\s+Health\s+savings\s+account", window)
    data.sched1_ira_deduction = _line(r"20\s+IRA\s+deduction", window)
    data.sched1_student_loan_interest = _line(r"21\s+Student\s+loan\s+interest", window)
    data.sched1_nol_deduction = _line(r"8\s*a\s+Net\s+operating\s+loss", window)


def _extract_schedule_a(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule A — Itemized Deductions.

    TurboTax Line 12 always reads "Standard deduction or itemized deductions
    (from Schedule A)" regardless of which was taken, so generic patterns like
    "SCHEDULE A" or "Itemized Deductions" fire as false positives.  We require
    the actual form-page header "SCHEDULE A (Form 1040)" which only appears when
    Schedule A was actually generated and filed.
    """
    data.sched_a_present = bool(
        re.search(r"SCHEDULE\s+A\s*\(Form\s+1040\)", text, re.IGNORECASE)
        or re.search(r"^SCHEDULE\s+A\b", text, re.IGNORECASE | re.MULTILINE)
    )
    if not data.sched_a_present:
        return
    window = _window_after(
        text,
        r"SCHEDULE\s+A\s*\(Form\s+1040\)|SCHEDULE\s+A\b",
        window=4000,
    )
    if not window:
        window = text
    data.sched_a_medical_dental = _line(r"4\s+Multiply\s+line\s+3|medical.*dental", window)
    data.sched_a_salt_total = _line(r"5\s*[ef]\s+Add\s+lines\s+5a|Total\s+taxes", window)
    data.sched_a_mortgage_interest = _line(r"8\s*a\s+Home\s+mortgage\s+interest", window)
    data.sched_a_charitable_cash = _line(r"11\s+Cash\s+or\s+check\s+contributions", window)
    data.sched_a_charitable_noncash = _line(r"12\s+Other\s+than\s+by\s+cash", window)
    data.sched_a_charitable_carryforward = _line(r"13\s+Carryover\s+from\s+prior\s+year", window)
    data.sched_a_investment_interest = _line(r"9\s+Investment\s+interest", window)
    data.sched_a_total_itemized = _line(r"17\s+Total\s+itemized\s+deductions", window)


def _extract_schedule_b(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule B — Interest & Dividends."""
    data.sched_b_present = _form_present(
        text,
        r"SCHEDULE\s+B\b",
        r"Schedule\s+B\s*\(Form",
        r"Part\s+III.*Foreign\s+Accounts",
    )
    if not data.sched_b_present:
        return
    window = _window_after(text, r"SCHEDULE\s+B\b|Schedule\s+B\s*\(Form", window=3000)
    if not window:
        window = text
    # Check for foreign account "Yes" answer in Part III question 7a
    if re.search(r"7\s*a[^\n]{0,60}Yes", window, re.IGNORECASE):
        data.sched_b_foreign_account = True
    elif re.search(r"foreign\s+(?:financial\s+)?account[^\n]{0,80}Yes", window, re.IGNORECASE):
        data.sched_b_foreign_account = True
    elif re.search(r"7\s*a[^\n]{0,60}No", window, re.IGNORECASE):
        data.sched_b_foreign_account = False


def _extract_schedule_c(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule C — Business Activity."""
    data.sched_c_present = _form_present(
        text,
        r"SCHEDULE\s+C\b",
        r"Schedule\s+C\s*\(Form",
        r"Profit\s+or\s+Loss\s+From\s+Business",
    )
    if not data.sched_c_present:
        return
    # Find each Schedule C occurrence
    for sch_m in re.finditer(
        r"SCHEDULE\s+C\b|Schedule\s+C\s*\(Form|Profit\s+or\s+Loss\s+From\s+Business",
        text, re.IGNORECASE,
    ):
        window = text[sch_m.start(): sch_m.start() + 3000]
        # Business name
        name_m = re.search(
            r"(?:A\s+)?Principal\s+business[^\n]{0,60}\n\s*([^\n]{2,60})",
            window, re.IGNORECASE,
        )
        if not name_m:
            name_m = re.search(
                r"Business\s+name[^\n]{0,10}\n\s*([^\n]{2,40})",
                window, re.IGNORECASE,
            )
        biz_name = name_m.group(1).strip() if name_m else None
        # EIN
        ein_m = re.search(
            r"(?:D\s+)?Employer\s+ID[^\n]{0,10}(\d{2}-\d{7})",
            window, re.IGNORECASE,
        )
        ein = ein_m.group(1) if ein_m else None
        # Accounting method
        method_m = re.search(
            r"(?:F\s+)?Accounting\s+method[^\n]{0,20}(Cash|Accrual|Other)",
            window, re.IGNORECASE,
        )
        method = method_m.group(1) if method_m else None
        # Net profit/loss (line 31)
        net = _line(r"31\s+Net\s+profit\s+or\s+\(?loss\)?", window)
        if biz_name or net is not None:
            data.sched_c_businesses.append({
                "name": biz_name,
                "ein": ein,
                "accounting_method": method,
                "net_profit_loss": net,
            })


def _extract_schedule_d(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule D — Capital Gains & Losses."""
    data.sched_d_present = _form_present(
        text,
        r"SCHEDULE\s+D\b",
        r"Capital\s+Gains\s+and\s+Losses",
    )
    if not data.sched_d_present:
        return
    window = _window_after(
        text,
        r"SCHEDULE\s+D\b|Capital\s+Gains\s+and\s+Losses",
        window=4000,
    )
    if not window:
        window = text
    data.sched_d_net_stcg = _line(r"7\s+Net\s+short.?term\s+capital\s+gain", window)
    data.sched_d_net_ltcg = _line(r"15\s+Net\s+long.?term\s+capital\s+gain", window)
    # Capital loss carryforward
    clc_m = re.search(
        r"(?:capital\s+loss\s+carryover|carryover\s+from.*prior\s+year)[^\n]{0,200}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if clc_m:
        data.sched_d_capital_loss_carryforward = parse_amount_token(clc_m.group(1).rstrip("."))


def _extract_schedule_e(text: str, data: PriorYearReturnData) -> None:
    """Extract Schedule E — Rental & Pass-Through Activity."""
    data.sched_e_present = _form_present(
        text,
        r"SCHEDULE\s+E\b",
        r"Supplemental\s+Income\s+and\s+Loss",
    )
    if not data.sched_e_present:
        return
    window = _window_after(
        text,
        r"SCHEDULE\s+E\b|Supplemental\s+Income\s+and\s+Loss",
        window=5000,
    )
    if not window:
        window = text
    # Rental property addresses (look for street address patterns in header area)
    addr_section = window[:1500]
    for addr_m in re.finditer(
        r"\d+\s+[A-Za-z][A-Za-z0-9\s\.\,\-]{5,50}(?:St|Ave|Rd|Blvd|Dr|Ln|Way|Ct|Pl|Hwy|Pkwy)\.?",
        addr_section,
    ):
        addr = addr_m.group(0).strip()
        if addr not in data.sched_e_rental_properties:
            data.sched_e_rental_properties.append(addr)
    # Income/loss totals
    data.sched_e_total_rental_income = _line(r"(?:23a|24)\s+Total\s+rents?\s+received", window)
    data.sched_e_total_rental_loss = _line(r"(?:23b|26)\s+Total\s+(?:rental\s+)?losses?", window)
    # K-1 indicators
    data.sched_e_k1_partnerships = bool(re.search(r"Partnership", window, re.IGNORECASE))
    data.sched_e_k1_s_corps = bool(re.search(r"S\s+corporation", window, re.IGNORECASE))
    data.sched_e_k1_trusts = bool(re.search(r"Trust|Estate", window, re.IGNORECASE))


def _extract_form_4562(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 4562 — Depreciation & Section 179."""
    data.form_4562_present = _form_present(
        text,
        r"Form\s+4562\b",
        r"Depreciation\s+and\s+Amortization",
    )
    if not data.form_4562_present:
        return
    window = _window_after(text, r"Form\s+4562\b|Depreciation\s+and\s+Amortization", window=4000)
    if not window:
        window = text
    s179_m = re.search(
        r"12\s+.*Section\s+179[^\n]{0,200}?\.\s+12\s+([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if s179_m:
        data.form_4562_section_179_deduction = parse_amount_token(s179_m.group(1).rstrip("."))
    else:
        data.form_4562_section_179_deduction = _line(r"12\s+.*Section\s+179", window)
    cf_m = re.search(
        r"13\s+Carryover\s+of\s+disallowed[^\n]{0,200}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_4562_section_179_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))
    bonus_m = re.search(
        r"(?:special|bonus)\s+depreciation[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if bonus_m:
        data.form_4562_bonus_depreciation = parse_amount_token(bonus_m.group(1).rstrip("."))


def _extract_form_8582(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8582 — Passive Activity Loss Limitations."""
    data.form_8582_present = _form_present(
        text,
        r"Form\s+8582\b",
        r"Passive\s+Activity\s+Loss\s+Limitations",
    )
    if not data.form_8582_present:
        return
    window = _window_after(
        text,
        r"Form\s+8582\b|Passive\s+Activity\s+Loss\s+Limitations",
        window=4000,
    )
    if not window:
        window = text
    pal_m = re.search(
        r"(?:unallowed\s+loss|carryforward)[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if pal_m:
        data.form_8582_pal_carryforward = parse_amount_token(pal_m.group(1).rstrip("."))
    rental_m = re.search(
        r"(?:rental\s+)?(?:real\s+estate\s+)?loss\s+carryforward[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if rental_m:
        data.form_8582_rental_loss_carryforward = parse_amount_token(rental_m.group(1).rstrip("."))


def _extract_form_8606(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8606 — Nondeductible IRAs."""
    data.form_8606_present = _form_present(
        text,
        r"Form\s+8606\b",
        r"Nondeductible\s+IRAs",
    )
    if not data.form_8606_present:
        return
    window = _window_after(text, r"Form\s+8606\b|Nondeductible\s+IRAs", window=4000)
    if not window:
        window = text
    basis_m = re.search(
        r"14\s+(?:Add\s+lines|Your\s+basis)[^\n]{0,200}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if basis_m:
        data.form_8606_ira_basis = parse_amount_token(basis_m.group(1).rstrip("."))
    nd_m = re.search(
        r"1\s+(?:Enter\s+your\s+)?nondeductible[^\n]{0,200}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if nd_m:
        data.form_8606_nondeductible_contributions = parse_amount_token(nd_m.group(1).rstrip("."))


def _extract_form_8829(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8829 — Home Office."""
    data.form_8829_present = _form_present(
        text,
        r"Form\s+8829\b",
        r"Expenses\s+for\s+Business\s+Use\s+of\s+Your\s+Home",
    )
    if not data.form_8829_present:
        return
    window = _window_after(
        text,
        r"Form\s+8829\b|Expenses\s+for\s+Business\s+Use\s+of\s+Your\s+Home",
        window=4000,
    )
    if not window:
        window = text
    cf_m = re.search(
        r"43\s+Carryover[^\n]{0,200}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_8829_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_form_8995(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8995 / 8995-A — Qualified Business Income Deduction."""
    data.form_8995_present = _form_present(
        text,
        r"Form\s+8995\b",
        r"Qualified\s+Business\s+Income\s+Deduction",
    )
    if not data.form_8995_present:
        return
    window = _window_after(
        text,
        r"Form\s+8995\b|Qualified\s+Business\s+Income\s+Deduction",
        window=4000,
    )
    if not window:
        window = text
    cf_m = re.search(
        r"(?:QBI\s+)?(?:loss\s+carryforward|carryover)[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_8995_qbi_loss_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_form_1116(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 1116 — Foreign Tax Credit."""
    data.form_1116_present = _form_present(
        text,
        r"Form\s+1116\b",
        r"Foreign\s+Tax\s+Credit",
    )
    if not data.form_1116_present:
        return
    window = _window_after(text, r"Form\s+1116\b|Foreign\s+Tax\s+Credit", window=4000)
    if not window:
        window = text
    data.form_1116_foreign_tax_credit = _line(r"35\s+Enter\s+the\s+smaller", window)
    cf_m = re.search(
        r"carryover\s+to[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_1116_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_form_3800(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 3800 — General Business Credit."""
    data.form_3800_present = _form_present(
        text,
        r"Form\s+3800\b",
        r"General\s+Business\s+Credit",
    )
    if not data.form_3800_present:
        return
    window = _window_after(text, r"Form\s+3800\b|General\s+Business\s+Credit", window=4000)
    if not window:
        window = text
    cf_m = re.search(
        r"carryforward\s+to[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_3800_credit_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_form_6251(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 6251 — Alternative Minimum Tax."""
    data.form_6251_present = _form_present(
        text,
        r"Form\s+6251\b",
        r"Alternative\s+Minimum\s+Tax",
    )
    if not data.form_6251_present:
        return
    window = _window_after(
        text,
        r"Form\s+6251\b|Alternative\s+Minimum\s+Tax",
        window=4000,
    )
    if not window:
        window = text
    data.form_6251_amt = _line(r"(?:11|19)\s+Alternative\s+minimum\s+tax", window)
    cf_m = re.search(
        r"(?:AMT\s+credit|minimum\s+tax\s+credit)\s+carryforward[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_6251_amt_credit_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_form_6252(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 6252 — Installment Sale Income."""
    data.form_6252_present = _form_present(
        text,
        r"Form\s+6252\b",
        r"Installment\s+Sale\s+Income",
    )
    if not data.form_6252_present:
        return
    window = _window_after(text, r"Form\s+6252\b|Installment\s+Sale\s+Income", window=4000)
    if not window:
        window = text
    gp_m = re.search(
        r"19\s+Gross\s+profit\s+percentage[^\n]{0,100}([\d.]+)\s*%",
        window, re.IGNORECASE,
    )
    if gp_m:
        try:
            data.form_6252_gross_profit_pct = float(gp_m.group(1))
        except ValueError:
            pass


def _extract_form_8283(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8283 — Noncash Charitable Contributions."""
    data.form_8283_present = _form_present(
        text,
        r"Form\s+8283\b",
        r"Noncash\s+Charitable\s+Contributions",
    )


def _extract_form_8889(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 8889 — Health Savings Accounts."""
    data.form_8889_present = _form_present(
        text,
        r"Form\s+8889\b",
        r"Health\s+Savings\s+Accounts",
    )
    if not data.form_8889_present:
        return
    window = _window_after(text, r"Form\s+8889\b|Health\s+Savings\s+Accounts", window=4000)
    if not window:
        window = text
    data.form_8889_hsa_contributions = _line(r"2\s+HSA\s+contributions", window)
    data.form_8889_excess_contributions = _line(r"18\s+Excess", window)


def _extract_form_7203(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 7203 — S-Corp Shareholder Stock and Debt Basis."""
    data.form_7203_present = _form_present(
        text,
        r"Form\s+7203\b",
        r"S\s+Corporation\s+Shareholder\s+Stock\s+and\s+Debt\s+Basis",
    )
    if not data.form_7203_present:
        return
    window = _window_after(
        text,
        r"Form\s+7203\b|S\s+Corporation\s+Shareholder\s+Stock\s+and\s+Debt\s+Basis",
        window=4000,
    )
    if not window:
        window = text
    # Stock basis: first amount near beginning
    stock_m = re.search(r"(?:stock\s+basis|basis\s+in\s+stock)[^\n]{0,200}([\d,]+\.(?:\d{2})?)", window, re.IGNORECASE)
    if stock_m:
        data.form_7203_stock_basis = parse_amount_token(stock_m.group(1).rstrip("."))
    # Debt basis
    debt_m = re.search(r"(?:debt\s+basis|basis\s+in\s+debt)[^\n]{0,200}([\d,]+\.(?:\d{2})?)", window, re.IGNORECASE)
    if debt_m:
        data.form_7203_debt_basis = parse_amount_token(debt_m.group(1).rstrip("."))


def _extract_form_6198(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 6198 — At-Risk Limitations."""
    data.form_6198_present = _form_present(
        text,
        r"Form\s+6198\b",
        r"At-Risk\s+Limitations",
    )
    if not data.form_6198_present:
        return
    window = _window_after(text, r"Form\s+6198\b|At-Risk\s+Limitations", window=4000)
    if not window:
        window = text
    cf_m = re.search(
        r"(?:at.risk\s+)?loss\s+carryforward[^\n]{0,100}([\d,]+\.(?:\d{2})?)",
        window, re.IGNORECASE,
    )
    if cf_m:
        data.form_6198_at_risk_carryforward = parse_amount_token(cf_m.group(1).rstrip("."))


def _extract_state_returns(text: str, data: PriorYearReturnData) -> None:
    """Detect state return filings from the PDF text."""
    state_pattern = re.compile(
        r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|"
        r"NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\b"
        r"[^\n]{0,60}(?:Department\s+of\s+Revenue|Tax\s+Commission|State\s+Income\s+Tax|"
        r"Resident\s+Return|Nonresident\s+Return|Individual\s+Income\s+Tax)",
        re.IGNORECASE,
    )
    found = set()
    for m in state_pattern.finditer(text):
        found.add(m.group(1).upper())
    # Also reverse pattern: "State Income Tax Return" with state code nearby
    for m in re.finditer(
        r"(?:Individual\s+Income\s+Tax|Resident\s+Return|Nonresident\s+Return)[^\n]{0,80}"
        r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|"
        r"NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\b",
        text, re.IGNORECASE,
    ):
        found.add(m.group(1).upper())
    data.state_returns_filed = sorted(found)


def _detect_elections(text: str, data: PriorYearReturnData) -> None:
    """Detect tax elections and continuity indicators."""
    data.election_real_estate_professional = _form_present(
        text,
        r"real\s+estate\s+professional",
        r"Real\s+Estate\s+Professional",
    )
    data.election_installment_sale = data.form_6252_present


def _extract_income_lines(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 1040 page 1 income lines 1a through 15."""

    # Line 1a — W-2 wages
    data.line_1a_w2_wages = _line(
        r"1\s*a\s+Total\s+amount\s+from\s+Form(?:\(s\))?\s+W-?2", text
    )
    # Line 1z — total wages (sum of 1a–1h)
    data.line_1z_total_wages = _line(
        r"1\s*z\s+Add\s+lines\s+1a", text
    )
    # Line 2b — taxable interest
    data.line_2b_taxable_interest = _line(
        r"2\s*b\s+Taxable\s+interest", text
    )
    # Line 3a — qualified dividends (same line as 3b; stop before "b Ordinary")
    data.line_3a_qualified_dividends = _line(
        r"3\s*a\s+Qualified\s+dividends",
        text,
        stop_pattern=r"\bb\s+Ordinary",
    )
    # Line 3b — ordinary dividends
    # TurboTax puts 3a and 3b on the same line: "3a ... 3a 281. b Ordinary ... 3b 6,933."
    # The "3b" label only appears as a reference after the dots, not as a standalone prefix.
    data.line_3b_ordinary_dividends = _line(
        r"b\s+Ordinary\s+dividends", text
    )
    # Line 4b — taxable IRA distributions
    # TurboTax: "4a IRA distributions . . . 4a  b Taxable amount . . . . 4b  210."
    # Use repeated line-ref pattern to find the actual 4b amount (avoids matching "8."
    # from "line 8" references that appear nearby on the same page).
    ira_m = re.search(
        r"4\s*a\s+IRA\s+distributions?[^\n]{0,200}?\.\s+4\s*[ab]\s+(\d[\d,]*\.(?:\d{2})?)",
        text, re.IGNORECASE,
    )
    data.line_4b_ira_taxable = parse_amount_token(ira_m.group(1).rstrip(".")) if ira_m else None

    # Line 5b — taxable pensions/annuities
    data.line_5b_pension_taxable = _line(
        r"5\s*[ab]\s+(?:Pensions?\s+and\s+annuities?|Taxable\s+amount)[^\n]{0,30}(?:\n[^\n]{0,60})?(?:5b|Taxable\s+amount)",
        text,
    )
    # Line 6b — taxable social security
    data.line_6b_ss_taxable = _line(
        r"6\s*[ab]\s+(?:Social\s+security\s+benefits?|Taxable\s+amount)[^\n]{0,30}(?:\n[^\n]{0,60})?(?:6b|Taxable\s+amount)",
        text,
    )
    # Line 7 — capital gain/loss
    data.line_7_capital_gain_loss = _line(
        r"7\s+Capital\s+gain\s+or\s+\(?loss\)?", text
    )
    # Line 8 — additional income (Schedule 1)
    data.line_8_other_income = _line(
        r"8\s+Additional\s+income\s+from\s+Schedule\s+1", text
    )
    # Line 9 — total income
    data.line_9_total_income = _line(
        r"9\s+Add\s+lines\s+1z", text
    )
    # Line 10 — adjustments
    data.line_10_adjustments = _line(
        r"10\s+Adjustments\s+to\s+income", text
    )
    # Line 11 — AGI
    data.line_11_agi = _line(
        r"11\s+Subtract\s+line\s+10\s+from\s+line\s+9[^\n]{0,30}adjusted\s+gross\s+income",
        text,
    )
    # Summary-page fallback: "Adjusted Gross Income $ 305,575.00"
    if data.line_11_agi is None:
        data.line_11_agi = _line(
            r"Adjusted\s+Gross\s+Income", text, require_decimal=True
        )
    # Line 12 — standard/itemized deductions
    data.line_12_deductions = _line(
        r"12\s+Standard\s+deduction\s+or\s+itemized", text
    )
    # Line 13 — QBI deduction.
    # TurboTax: "13 Qualified business income deduction from Form 8995 ... . . . 13 2."
    # The repeated line-number "13" precedes the amount after the dotted leader.
    # Match it directly to avoid false-positive form numbers like 8995.
    qbi_m = re.search(
        r"13\s+Qualified\s+business\s+income\s+deduction[^\n]{0,200}?\.\s+13\s+(\d[\d,]*\.(?:\d{2})?)",
        text, re.IGNORECASE,
    )
    data.line_13_qbi_deduction = parse_amount_token(qbi_m.group(1).rstrip(".")) if qbi_m else None
    # Line 15 — taxable income (label spans ~60 chars before the amount)
    data.line_15_taxable_income = _line(
        r"15\s+Subtract\s+line\s+14\s+from\s+line\s+11",
        text,
    )
    # Summary-page fallback
    if data.line_15_taxable_income is None:
        data.line_15_taxable_income = _line(
            r"Taxable\s+Income", text, require_decimal=True
        )


def _extract_tax_and_payment_lines(text: str, data: PriorYearReturnData) -> None:
    """Extract Form 1040 page 2 tax, credits, and payment lines."""

    # Line 16 — income tax
    data.line_16_tax = _line(
        r"16\s+Tax\s+\(see\s+instructions\)", text
    )
    # Line 24 — total tax
    data.line_24_total_tax = _line(
        r"24\s+Add\s+lines\s+22\s+and\s+23[^\n]{0,40}total\s+tax",
        text,
    )
    # Summary-page fallback
    if data.line_24_total_tax is None:
        data.line_24_total_tax = _line(
            r"Total\s+Tax", text, require_decimal=True
        )

    # Line 25a — W-2 withholding
    # TurboTax layout: "25 Federal income tax withheld from:\na Form(s) W-2 ... 25a 40,202."
    data.line_25a_w2_withholding = _line(
        r"(?:25\s*a|a\s+Form(?:\(s\))?\s+W-?2)", text,
        stop_pattern=r"\bb\s+Form",
    )
    # Line 25b — 1099 withholding
    data.line_25b_1099_withholding = _line(
        r"(?:25\s*b|b\s+Form(?:\(s\))?\s+1099)", text,
        stop_pattern=r"\bc\s+Other",
    )
    # Line 25d — total withholding
    data.line_25d_total_withholding = _line(
        r"25\s*d\s+Add\s+lines\s+25a", text
    )
    # Summary-page fallback
    if data.line_25d_total_withholding is None:
        data.line_25d_total_withholding = _line(
            r"Total\s+Payments[/\\]Credits", text, require_decimal=True
        )

    # Line 26 — estimated tax payments
    # The label contains "20XX estimated tax payments applied from 20YY return" so we
    # stop searching before "applied from" to avoid capturing the prior-year number.
    data.line_26_estimated_payments = _line(
        r"26\s+20\d{2}\s+estimated\s+tax\s+payments",
        text,
        stop_pattern=r"applied\s+from",
    )
    # Line 33 — total payments
    data.line_33_total_payments = _line(
        r"33\s+Add\s+lines\s+25d", text
    )
    # Line 34 — overpayment
    data.line_34_overpayment = _line(
        r"34\s+If\s+line\s+33\s+is\s+more\s+than\s+line\s+24", text
    )
    # Line 35a — refund
    data.line_35a_refund = _line(
        r"35\s*a\s+Amount\s+of\s+line\s+34\s+you\s+want\s+refunded", text
    )
    # Line 37 — amount owed
    # TurboTax wraps this across two lines ("37 Subtract... This is the amount you owe.\n
    # For details ... 37 1,399.") so we use multiline search.
    data.line_37_amount_owed = _line(
        r"37\s+Subtract\s+line\s+33\s+from\s+line\s+24",
        text,
        multiline=True,
    )
    # Summary-page fallbacks for refund/balance due
    if data.line_35a_refund is None and data.line_37_amount_owed is None:
        refund_m = re.search(
            r"(?:Refund|Amount\s+Refunded)[^\n]{0,20}\$\s*([\d,]+\.\d{2})",
            text, re.IGNORECASE,
        )
        if refund_m:
            data.line_35a_refund = parse_amount_token(refund_m.group(1))
        balance_m = re.search(
            r"(?:Balance\s+[Dd]ue|Payment\s+[Dd]ue|Amount\s+[Oo]wed)[^\n]{0,20}\$\s*([\d,]+\.\d{2})",
            text, re.IGNORECASE,
        )
        if balance_m:
            data.line_37_amount_owed = parse_amount_token(balance_m.group(1))

    # Line 38 — estimated tax penalty
    data.line_38_estimated_tax_penalty = _line(
        r"38\s+Estimated\s+tax\s+penalty", text
    )


def _score_confidence(data: PriorYearReturnData) -> float:
    """Compute a 0–1 confidence score based on populated critical fields."""
    populated = sum(
        1 for f in _CONFIDENCE_FIELDS
        if getattr(data, f, None) not in (None, "")
    )
    base = populated / len(_CONFIDENCE_FIELDS)
    bonus = 0.05 if data.line_11_agi is not None else 0.0
    return round(min(1.0, base + bonus), 2)


def parse_prior_year_return_text(
    text: str,
    fallback_year: Optional[int] = None,
) -> PriorYearReturnData:
    """Parse extracted text from a prior-year Form 1040 PDF.

    Args:
        text: Raw text extracted from the PDF (all pages concatenated).
        fallback_year: Use this year if the year cannot be detected from the text.

    Returns:
        A populated PriorYearReturnData instance.
    """
    data = PriorYearReturnData()
    text = normalize_extracted_text(text)

    # --- Year ---
    data.year = _extract_year(text)
    if data.year is None and fallback_year is not None:
        data.year = fallback_year

    # --- Filing status ---
    data.filing_status = _extract_filing_status(text)

    # --- Names & SSNs ---
    (
        data.taxpayer_name,
        data.taxpayer_ssn,
        data.spouse_name,
        data.spouse_ssn,
    ) = _extract_names_and_ssns(text)

    # --- Address ---
    (
        data.address,
        data.city,
        data.state,
        data.zip_code,
    ) = _extract_address(text)

    # --- Occupations ---
    _extract_occupations(text, data)

    # --- Dependents ---
    _extract_dependents(text, data)

    # --- Extension indicator ---
    _extract_extension(text, data)

    # --- Income lines (page 1) ---
    _extract_income_lines(text, data)

    # --- Tax & payment lines (page 2) ---
    _extract_tax_and_payment_lines(text, data)

    # --- Refund applied forward (line 36) ---
    _extract_refund_applied_forward(text, data)

    # --- Schedule 1 adjustments ---
    _extract_schedule_1_adjustments(text, data)

    # --- Schedule A ---
    _extract_schedule_a(text, data)

    # --- Schedule B ---
    _extract_schedule_b(text, data)

    # --- Schedule C ---
    _extract_schedule_c(text, data)

    # --- Schedule D ---
    _extract_schedule_d(text, data)

    # --- Schedule E ---
    _extract_schedule_e(text, data)

    # --- Form 4562 ---
    _extract_form_4562(text, data)

    # --- Form 8582 ---
    _extract_form_8582(text, data)

    # --- Form 8606 ---
    _extract_form_8606(text, data)

    # --- Form 8829 ---
    _extract_form_8829(text, data)

    # --- Form 8995 ---
    _extract_form_8995(text, data)

    # --- Form 1116 ---
    _extract_form_1116(text, data)

    # --- Form 3800 ---
    _extract_form_3800(text, data)

    # --- Form 6251 ---
    _extract_form_6251(text, data)

    # --- Form 6252 ---
    _extract_form_6252(text, data)

    # --- Form 8283 ---
    _extract_form_8283(text, data)

    # --- Form 8889 ---
    _extract_form_8889(text, data)

    # --- Form 7203 ---
    _extract_form_7203(text, data)

    # --- Form 6198 ---
    _extract_form_6198(text, data)

    # --- State returns ---
    _extract_state_returns(text, data)

    # --- Elections ---
    _detect_elections(text, data)

    # --- Confidence ---
    data.confidence = _score_confidence(data)

    _log.debug(
        "prior_year_return: year=%s agi=%s total_tax=%s confidence=%.2f",
        data.year,
        data.line_11_agi,
        data.line_24_total_tax,
        data.confidence,
    )
    return data
