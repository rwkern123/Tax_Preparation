from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text, parse_amount_token
from src.models import Form1098Data


def _money(pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(pattern, text)


def _amt(raw: str) -> Optional[float]:
    """Parse an already-matched numeric string like '17,704.08'."""
    return parse_amount_token(raw.replace(",", ""))


def parse_1098_text(text: str) -> Form1098Data:
    data = Form1098Data()
    text = normalize_extracted_text(text)

    # --- Year ---
    # Prefer explicit "YEAR: 2024" label from Rocket/Mr.Cooper escrow header.
    year_m = re.search(r"\bYEAR:\s*(20\d{2})\b", text, re.IGNORECASE)
    if year_m:
        data.year = int(year_m.group(1))
    else:
        cal_m = re.search(r"For\s+calendar\s+year\s*\n?\s*(20\d{2})", text, re.IGNORECASE)
        if cal_m:
            data.year = int(cal_m.group(1))
        else:
            generic_m = re.search(r"\b(20\d{2})\b", text)
            if generic_m:
                data.year = int(generic_m.group(1))

    # --- Lender name ---
    # Strategy 1: escrow summary line "BORROWER_NAME  LenderName\nYEAR: 20XX".
    # pdfplumber linearises the two-column header, placing borrower (ALL-CAPS)
    # and lender (mixed-case) on the same line, followed by "YEAR:".
    lender_m = re.search(
        r"([A-Z]+(?:\s+[A-Z]+)+)\s+([A-Z][a-z][^\n]{3,120})\nYEAR:\s*\d{4}",
        text,
    )
    if lender_m:
        data.lender_name = lender_m.group(2).strip()[:120]
    else:
        # Strategy 2: after RECIPIENT/LENDER label block — name is 3 lines below;
        # strip trailing linearisation boilerplate ("and the cost and value...").
        lender_m2 = re.search(
            r"RECIPIENT.{0,10}LENDER.{0,10}name[^\n]*\n[^\n]*\n[^\n]*\n"
            r"([A-Z][^\n]{5,120}?)(?:\s+and\s+the\s+cost|\s+For\s+calendar|\s+\d{4}\s*$)",
            text, re.IGNORECASE,
        )
        if lender_m2:
            data.lender_name = lender_m2.group(1).strip()[:120]
        else:
            # Strategy 3: simple labelled field (non-linearised PDFs)
            lender_m3 = re.search(r"(?:Lender|Recipient)\s*(?:name)?[:\s]+([^\n]+)", text, re.IGNORECASE)
            if lender_m3:
                data.lender_name = lender_m3.group(1).strip()[:120]

    # --- Payer / Borrower name ---
    # In linearised PDFs, the actual name sits 1–2 lines *below* the label because
    # adjacent form columns are interleaved.  The name itself is ALL-CAPS.
    def _is_valid_borrower(s: str) -> bool:
        return not re.search(r"\bPoints\b|\bStreet\b|\bCity\b|\bNumber\b|\bMortgage\b", s, re.IGNORECASE)

    payer_m = re.search(
        r"PAYER.{0,10}BORROWER.{0,10}name[^\n]*\n(?:[^\n]*\n){0,2}"
        r"([A-Z][A-Z\s]{2,60}?)(?=\s+\d|\s*$)",
        text, re.IGNORECASE,
    )
    if payer_m and _is_valid_borrower(payer_m.group(1)):
        data.payer_name = payer_m.group(1).strip()[:120]
    if not data.payer_name:
        payer_m2 = re.search(r"(?:Payer|Borrower)\s*(?:name)?[:\s]+([^\n]+)", text, re.IGNORECASE)
        if payer_m2:
            candidate = payer_m2.group(1).strip()
            if _is_valid_borrower(candidate):
                data.payer_name = candidate[:120]

    # Borrower names list (same search, collect all hits)
    raw_borrowers = re.findall(
        r"PAYER.{0,10}BORROWER.{0,10}name[^\n]*\n(?:[^\n]*\n){0,2}"
        r"([A-Z][A-Z\s]{2,60}?)(?=\s+\d|\s*$)",
        text, re.IGNORECASE,
    )
    data.borrower_names = [b.strip()[:120] for b in raw_borrowers if _is_valid_borrower(b.strip())]

    # --- Mortgage interest received (Box 1) ---
    # Strategy 1: escrow summary section.  pdfplumber interleaves two columns so
    # "MORTGAGE INTEREST RECEIVED FROM" and "PAYER(S)/BORROWER(S): $X" may be
    # separated by an unrelated column line — skip up to 2 intervening lines.
    mi_m = re.search(
        r"MORTGAGE\s+INTEREST\s+RECEIVED\s+FROM\s*\n"
        r"(?:[^\n]*\n){0,2}PAYER[^\n]*:\s*\$([\d,]+(?:\.\d{2})?)",
        text, re.IGNORECASE,
    )
    if mi_m:
        data.mortgage_interest_received = _amt(mi_m.group(1))
    else:
        # Strategy 2: box 1 label; amount follows on next line after "$"
        mi_m2 = re.search(
            r"1\s+Mortgage\s+interest\s+received\s+from\s+payer[^\n]*\n\$?\s*([\d,]+(?:\.\d{2})?)",
            text, re.IGNORECASE,
        )
        if mi_m2:
            data.mortgage_interest_received = _amt(mi_m2.group(1))
        else:
            # Strategy 3: generic label (works on non-linearised PDFs)
            data.mortgage_interest_received = _money(
                r"(?:1\.?\s*Mortgage\s+interest\s+received|Mortgage\s+interest\s+received)", text
            )

    # --- Outstanding mortgage principal (Box 2) ---
    # Strategy 1: "BEG BAL: $X" from escrow principal reconciliation section
    principal_m = re.search(r"BEG\s+BAL:\s*\$([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
    if principal_m:
        data.mortgage_principal_outstanding = _amt(principal_m.group(1))
    else:
        # Strategy 2: box 2 label which spans two lines in linearised PDFs
        # Text pattern: "2 Outstanding mortgage\nprincipal ... $ 411,332.67 ..."
        principal_m2 = re.search(
            r"2\s+Outstanding\s+mortgage\s*\n?principal[^\$\n]{0,100}\$\s*([\d,]+(?:\.\d{2})?)",
            text, re.IGNORECASE | re.DOTALL,
        )
        if principal_m2:
            data.mortgage_principal_outstanding = _amt(principal_m2.group(1))
        else:
            data.mortgage_principal_outstanding = _money(
                r"(?:2\.?\s*Outstanding\s+mortgage\s+principal|Outstanding\s+mortgage\s+principal)", text
            )

    # --- Mortgage insurance premiums (Box 5) ---
    # Box label sometimes wraps: "5 Mortgage insurance\npremiums"
    mip_m = re.search(
        r"5\s+Mortgage\s+insurance\s*\n?premiums[^\$\n]{0,80}\$\s*([\d,]+(?:\.\d{2})?)",
        text, re.IGNORECASE,
    )
    if mip_m:
        data.mortgage_insurance_premiums = _amt(mip_m.group(1))
    else:
        data.mortgage_insurance_premiums = _money(
            r"(?:5\.?\s*Mortgage\s+insurance\s+premiums|Mortgage\s+insurance\s+premiums)", text
        )

    # --- Points paid (Box 6) ---
    data.points_paid = _money(
        r"(?:6\.?\s*Points\s+paid\s+on\s+purchase\s+of\s+principal\s+residence|Points\s+paid)", text
    )

    # --- Real estate taxes (Box 10) ---
    # Strategy 1: "PROPERTY TAXES: $X" from the escrow disbursements section
    ret_m = re.search(r"PROPERTY\s+TAXES:\s*\$([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
    if ret_m:
        data.real_estate_taxes = _amt(ret_m.group(1))
    else:
        data.real_estate_taxes = _money(
            r"(?:10\.?\s*(?:Real\s+estate\s+taxes|Other\s+[\u2014\-]?\s*Real\s+estate)|Real\s+estate\s+taxes)",
            text,
        )

    # --- Confidence ---
    populated = sum(
        1
        for value in [
            data.lender_name,
            data.payer_name,
            data.borrower_names or None,
            data.mortgage_interest_received,
            data.points_paid,
            data.mortgage_insurance_premiums,
            data.real_estate_taxes,
            data.mortgage_principal_outstanding,
        ]
        if value not in (None, "", [])
    )
    data.confidence = round(min(1.0, populated / 8), 2)
    return data
