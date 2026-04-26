from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import FormSSA1099Data


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def _parenthesized_amount(pattern: str, text: str) -> Optional[float]:
    """Extract a dollar amount that may be in parentheses (negative notation on SSA-1099)."""
    m = re.search(pattern + r"[^\d(]{0,30}\(?\$?([\d,]+(?:\.\d{2})?)\)?", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_ssa_1099_text(text: str) -> FormSSA1099Data:
    data = FormSSA1099Data()
    text = normalize_extracted_text(text)

    # Tax year
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Box 1 — Beneficiary name
    name_match = re.search(
        r"(?:box\s*1\.?\s*)?(?:beneficiary['']?s?\s+)?name[^:\n]{0,20}[:\s]+([^\n]{2,80})",
        text, re.IGNORECASE,
    )
    if name_match:
        candidate = name_match.group(1).strip()
        # Exclude lines that look like labels rather than a real name
        if not re.search(r"beneficiary|social\s+security|number|SSN", candidate, re.IGNORECASE):
            data.beneficiary_name = candidate[:120]

    # Box 2 — Beneficiary's SSN (may be partially masked)
    ssn_match = re.search(
        r"(?:box\s*2\.?\s*)?beneficiary['']?s?\s+social\s+security\s+number[^\d]{0,15}"
        r"([\dX*]{3}-[\dX*]{2}-\d{4}|\d{9}|\*{5}\d{4})",
        text, re.IGNORECASE,
    )
    if ssn_match:
        data.beneficiary_ssn = ssn_match.group(1).strip()

    # Box 3 — Total Benefits Paid
    data.box3_benefits_paid = _money(r"(?:box\s*3\.?\s*)?(?:total\s+)?benefits?\s+paid", text)

    # Box 4 — Benefits Repaid to SSA
    data.box4_benefits_repaid = _money(
        r"(?:box\s*4\.?\s*)?benefits?\s+repaid(?:\s+to\s+(?:ssa|social\s+security))?", text
    )

    # Box 5 — Net Benefits (key tax number → Form 1040 Line 6a)
    # The form may show a negative amount in parentheses when repayments exceed gross.
    net_raw = re.search(
        r"(?:box\s*5\.?\s*)?net\s+(?:social\s+security\s+)?benefits?[^$\d(]{0,30}"
        r"(\(?\$?[\d,]+(?:\.\d{2})?\)?)",
        text, re.IGNORECASE,
    )
    if net_raw:
        raw_str = net_raw.group(1)
        data.box5_is_negative = raw_str.startswith("(")
        try:
            data.box5_net_benefits = float(raw_str.strip("()$").replace(",", ""))
            if data.box5_is_negative:
                data.box5_net_benefits = -data.box5_net_benefits
        except ValueError:
            pass

    # Derive Box 5 if absent but Boxes 3 & 4 are present
    if data.box5_net_benefits is None and data.box3_benefits_paid is not None:
        repaid = data.box4_benefits_repaid or 0.0
        data.box5_net_benefits = round(data.box3_benefits_paid - repaid, 2)
        if data.box5_net_benefits < 0:
            data.box5_is_negative = True

    # Box 6 — Voluntary Federal Income Tax Withheld
    data.box6_voluntary_tax_withheld = _money(
        r"(?:box\s*6\.?\s*)?(?:voluntary\s+)?federal\s+(?:income\s+)?tax\s+withheld", text
    )

    # Box 8 — Claim Number (used for all SSA correspondence)
    claim_match = re.search(
        r"(?:box\s*8\.?\s*)?claim\s+number[^:\n]{0,10}[:\s]+([\w\d-]{4,20})",
        text, re.IGNORECASE,
    )
    if claim_match:
        data.box8_claim_number = claim_match.group(1).strip()

    # Description of Amount in Box 3 sub-items
    # "Paid by check or direct deposit" — amount actually received in hand
    data.box3_paid_by_check = _money(
        r"paid\s+by\s+(?:check\s+or\s+)?direct\s+deposit", text
    )

    # Medicare premiums deducted from benefits (Part B, C, or D — shown as one line item)
    data.medicare_premiums = _money(
        r"medicare\s+(?:(?:part\s+[bcd]|insurance)\s+)?premiums?(?:\s+deducted)?", text
    )

    # Attorney fees withheld from benefits and paid directly to attorney
    data.attorney_fees_withheld = _money(r"attorney\s+fees?(?:\s+withheld)?", text)

    # Lump-sum prior-year amount — asterisk notation:
    # "*Box 3 includes $X paid in 2025 for 2024, 2023, and other tax years"
    lump_match = re.search(
        r"\*\s*box\s*3\s+includes?\s+\$?([\d,]+(?:\.\d{2})?)\s+paid\s+in\s+\d{4}",
        text, re.IGNORECASE,
    )
    if lump_match:
        try:
            data.lump_sum_prior_years = float(lump_match.group(1).replace(",", ""))
        except ValueError:
            pass
    # Fallback: look for "lump.sum" adjacent to a dollar figure
    if data.lump_sum_prior_years is None:
        data.lump_sum_prior_years = _money(r"lump[-\s]sum\s+(?:benefit\s+)?payments?", text)

    # Full description block
    desc_match = re.search(
        r"description\s+of\s+amount\s+in\s+box\s+3[^:]*:?\s*([^\n]{1,300})",
        text, re.IGNORECASE,
    )
    if desc_match:
        data.box3_description = desc_match.group(1).strip()[:300]

    data.is_corrected = bool(re.search(r"\bCORRECTED\b", text, re.IGNORECASE))

    # Confidence scoring
    filled = [
        data.beneficiary_name,
        data.beneficiary_ssn,
        data.box3_benefits_paid,
        data.box4_benefits_repaid,
        data.box5_net_benefits,
        data.box6_voluntary_tax_withheld,
    ]
    populated = sum(1 for f in filled if f not in (None, "", False))
    if data.year and data.box5_net_benefits is not None:
        populated += 1
    data.confidence = round(min(1.0, populated / 7), 2)

    return data
