from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text, parse_amount_token
from src.models import Brokerage1099Data


def _money(label_pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(label_pattern, text)


def _parse_covered_noncovered_totals(text: str) -> dict:
    """Extract short/long-term totals split by IRS-reporting status.

    Brokers format these as a table sectioned by a heading like
    "BASIS IS REPORTED TO THE IRS" or "BASIS IS NOT REPORTED TO THE IRS"
    (or "BASIS IS MISSING").  Under each heading the rows contain
    "Total Short-Term" and "Total Long-Term" followed by a dollar amount
    that represents the realized gain/loss for that category.

    Returns a dict with keys: short_term_covered, short_term_noncovered,
    long_term_covered, long_term_noncovered (values may be None).
    """
    result: dict = {
        "short_term_covered": None,
        "short_term_noncovered": None,
        "long_term_covered": None,
        "long_term_noncovered": None,
    }

    # Amount token: optional leading minus or parens, optional $, digits with commas, optional .xx
    _AMT = r"\(?-?\$?\s*[\d,]+(?:\.\d{2})?\)?"

    # Split text into sections on each "BASIS IS …" or "Box A/B/D/E" or "COVERED/NONCOVERED" heading.
    section_re = re.compile(
        r"(basis\s+is\s+(?:reported\s+to\s+the\s+irs|not\s+reported(?:\s+to\s+the\s+irs)?|missing)"
        r"|transactions\s+(?:reported\s+)?(?:for\s+which\s+basis\s+is\s+(?:not\s+)?reported)"
        r"|box\s+[abcdef]\s*[:\-]?\s*(?:short|long)[-\s]term\s+(?:covered|noncovered)"
        r"|\b(?:covered|noncovered)\s+(?:short|long)[-\s]term)",
        re.IGNORECASE,
    )
    parts = section_re.split(text)
    # parts alternates: [pre-heading-text, heading, body, heading, body, ...]
    # Walk pairs of (heading, body)
    i = 1
    while i < len(parts) - 1:
        heading = parts[i].lower()
        body = parts[i + 1]
        i += 2

        # Determine whether this section is "covered" (reported) or "noncovered"
        is_noncovered = bool(re.search(r"not\s+reported|missing|noncovered|box\s+[bef]\b", heading))
        if is_noncovered:
            st_key = "short_term_noncovered"
            lt_key = "long_term_noncovered"
        else:
            st_key = "short_term_covered"
            lt_key = "long_term_covered"

        st_match = re.search(
            r"total\s+short[-\s]term[^\d\-\($]{0,80}(" + _AMT + r")",
            body,
            re.IGNORECASE,
        )
        if st_match:
            result[st_key] = parse_amount_token(st_match.group(1))

        lt_match = re.search(
            r"total\s+long[-\s]term[^\d\-\($]{0,80}(" + _AMT + r")",
            body,
            re.IGNORECASE,
        )
        if lt_match:
            result[lt_key] = parse_amount_token(lt_match.group(1))

    return result


def parse_brokerage_1099_text(text: str) -> Brokerage1099Data:
    data = Brokerage1099Data()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    broker_match = re.search(r"(?:Broker|Payer|Financial Institution)[:\s]+(.+)", text, re.IGNORECASE)
    if broker_match:
        data.broker_name = broker_match.group(1).strip()[:120]

    acct_match = re.search(r"account\s+number[:\s]+([\d\-]+)", text, re.IGNORECASE)
    if acct_match:
        data.account_number = acct_match.group(1).strip()

    # OCR-tolerant patterns: Tesseract commonly misreads 'i' as 'l' or '1' in IRS form fonts.
    data.div_ordinary = _money(r"ord[il1]nary\s+div[il1]dends", text)
    data.div_qualified = _money(r"qual[il1]f[il1]ed\s+div[il1]dends", text)
    data.div_cap_gain_distributions = _money(r"capital\s+gain\s+distributions", text)
    data.div_foreign_tax_paid = _money(r"foreign\s+tax\s+paid", text)
    data.div_section_199a = _money(r"section\s*199a\s+div", text)

    data.int_interest_income = _money(r"interest\s+income", text)
    data.int_us_treasury = _money(r"us\s+treasury\s+interest|treasury\s+obligations", text)

    data.section_1256_net_gain_loss = _money(
        r"aggregate\s+profit\s+or\s+(?:loss|.loss.)|total.*section\s*1256", text
    )

    summary_labels = {
        "proceeds": r"(?:net|total|gross)\s+proceeds",
        "cost_basis": r"(?:net\s+)?cost\s+(?:or\s+other\s+)?basis",
        "wash_sales": r"wash\s+sale(?:\s+loss(?:\s+disallowed)?)?",
        "short_term_gain_loss": r"(?:net\s+)?short[-\s]term\s+(?:gain|loss)",
        "long_term_gain_loss": r"(?:net\s+)?long[-\s]term\s+(?:gain|loss)",
    }
    for key, pattern in summary_labels.items():
        data.b_summary[key] = _money(pattern, text)

    covered = _parse_covered_noncovered_totals(text)
    data.b_short_term_covered = covered["short_term_covered"]
    data.b_short_term_noncovered = covered["short_term_noncovered"]
    data.b_long_term_covered = covered["long_term_covered"]
    data.b_long_term_noncovered = covered["long_term_noncovered"]

    checkable_values = [
        data.div_ordinary,
        data.div_qualified,
        data.div_cap_gain_distributions,
        data.div_foreign_tax_paid,
        data.div_section_199a,
        data.int_interest_income,
        data.int_us_treasury,
        data.section_1256_net_gain_loss,
        data.b_short_term_covered,
        data.b_short_term_noncovered,
        data.b_long_term_covered,
        data.b_long_term_noncovered,
        *data.b_summary.values(),
    ]
    populated = sum(1 for v in checkable_values if v is not None)
    data.confidence = round(min(1.0, populated / len(checkable_values)), 2)
    return data
