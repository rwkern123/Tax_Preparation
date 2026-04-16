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
        r"([A-Za-z][A-Za-z\s\.\-']{1,40}?)\s{2,}(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
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

    # -- Spouse (MFJ) --
    sp_m = re.search(
        r"(?:joint\s+return[^\n]*\n\s*)"
        r"([A-Za-z][A-Za-z\s\.\-']{1,40}?)\s{2,}(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
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
            r"\s{3,}(\d{3}[\s\-]\d{2}[\s\-]\d{4})",
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

    # --- Income lines (page 1) ---
    _extract_income_lines(text, data)

    # --- Tax & payment lines (page 2) ---
    _extract_tax_and_payment_lines(text, data)

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
