from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import normalize_extracted_text, parse_amount_token
from src.models import ScheduleCData


def _money_line(label_pattern: str, text: str) -> Optional[float]:
    """Extract a Schedule C line amount.

    Schedule C lines often render as "8 Advertising . . . . . 8 5,432.00"
    where the line number repeats between label and value, so the helper must
    allow digits in the gap. Decimal-required matching prevents the repeated
    line number from being captured when a field is empty.
    """
    m = re.search(
        label_pattern + r"[^\n]{0,80}?(\(?-?\$?\s*[\d,]+\.\d{2}\)?)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    return parse_amount_token(m.group(1))


def _yes_no(label_pattern: str, text: str) -> Optional[bool]:
    """Extract a Yes/No checkbox answer following a label.

    Adjacency-based detection: a marker ([X], ☒, ✓) within ~3 chars of Yes/No
    determines the answer. The "word immediately followed by marker" form
    (e.g. "Yes [X]") takes precedence over the "marker immediately followed
    by word" form, since the trailing-marker layout is most common in
    preparer-software output.
    """
    m = re.search(label_pattern, text, re.IGNORECASE)
    if not m:
        return None
    # Limit the window to the rest of the current line — extending across newlines
    # risks capturing a Yes/No answer from the next question.
    nl = text.find("\n", m.end())
    end = (nl if 0 <= nl - m.end() <= 250 else m.end() + 250)
    window = text[m.end() : end]
    marker = r"(?:\[X\]|☒|✓)"
    # Trailing-marker form: "Yes [X]" / "No [X]"
    if re.search(rf"\bYes\b\s{{0,3}}{marker}", window, re.IGNORECASE):
        return True
    if re.search(rf"\bNo\b\s{{0,3}}{marker}", window, re.IGNORECASE):
        return False
    # Leading-marker form: "[X] Yes" / "[X] No"
    if re.search(rf"{marker}\s{{0,3}}\bYes\b", window, re.IGNORECASE):
        return True
    if re.search(rf"{marker}\s{{0,3}}\bNo\b", window, re.IGNORECASE):
        return False
    return None


def _checkbox_after(label_pattern: str, text: str, window_chars: int = 80) -> bool:
    """Return True if a checked marker appears within window_chars surrounding the label.

    Some preparer software places the marker before the label
    (e.g. "32b [X] Some investment is not at risk"), others after, so check both sides.
    """
    m = re.search(label_pattern, text, re.IGNORECASE)
    if not m:
        return False
    pre_window = text[max(0, m.start() - 30) : m.start()]
    post_window = text[m.end() : m.end() + window_chars]
    marker = r"\[X\]|☒|✓"
    return bool(re.search(marker, pre_window) or re.search(marker, post_window))


def _accounting_method(text: str) -> Optional[str]:
    m = re.search(r"\bF\s+Accounting\s+method[^\n]{0,300}", text, re.IGNORECASE)
    if not m:
        return None
    window = m.group(0)
    if re.search(r"(?:\[X\]|☒|✓|X)\s*\(?1\)?\s*Cash|\(1\)\s*(?:\[X\]|☒|✓|X)\s*Cash|Cash\s*(?:\[X\]|☒|✓)", window, re.IGNORECASE):
        return "cash"
    if re.search(r"(?:\[X\]|☒|✓|X)\s*\(?2\)?\s*Accrual|\(2\)\s*(?:\[X\]|☒|✓|X)\s*Accrual|Accrual\s*(?:\[X\]|☒|✓)", window, re.IGNORECASE):
        return "accrual"
    if re.search(r"(?:\[X\]|☒|✓|X)\s*\(?3\)?\s*Other|\(3\)\s*(?:\[X\]|☒|✓|X)\s*Other", window, re.IGNORECASE):
        return "other"
    return None


def _inventory_method(text: str) -> Optional[str]:
    m = re.search(r"33\s+Method\(s\)\s+used[^\n]{0,300}", text, re.IGNORECASE)
    if not m:
        return None
    window = m.group(0)
    if re.search(r"(?:\[X\]|☒|✓|X)\s*a?\s*Cost\b", window, re.IGNORECASE):
        return "cost"
    if re.search(r"(?:\[X\]|☒|✓|X)\s*b?\s*Lower\s+of\s+cost", window, re.IGNORECASE):
        return "lcm"
    if re.search(r"(?:\[X\]|☒|✓|X)\s*c?\s*Other", window, re.IGNORECASE):
        return "other"
    return None


def _parse_other_expenses(text: str) -> list[dict]:
    """Parse Part V free-form description/amount rows preceding line 48."""
    m = re.search(
        r"Part\s+V\s+Other\s+Expenses[\s\S]{0,3000}?48\s+Total\s+other\s+expenses",
        text,
        re.IGNORECASE,
    )
    if not m:
        return []
    block = m.group(0)
    # Strip the section header and the line-48 trailer
    block = re.sub(r"Part\s+V\s+Other\s+Expenses[^\n]*\n?", "", block, count=1, flags=re.IGNORECASE)
    block = re.sub(r"\n[^\n]*48\s+Total\s+other\s+expenses[\s\S]*$", "", block, flags=re.IGNORECASE)

    items: list[dict] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Match "<description>  <amount>" — amount must have decimals to avoid noise
        match = re.match(r"^(.+?)\s+(\(?-?\$?\s*[\d,]+\.\d{2}\)?)\s*$", line)
        if not match:
            continue
        desc = match.group(1).strip().rstrip(".").strip()
        amt = parse_amount_token(match.group(2))
        if desc and amt is not None and len(desc) <= 80:
            items.append({"description": desc, "amount": amt})
    return items


def parse_schedule_c_text(text: str) -> ScheduleCData:
    data = ScheduleCData()
    text = normalize_extracted_text(text)

    year_match = re.search(r"Schedule\s+C[^\n]{0,80}?(20\d{2})", text, re.IGNORECASE) \
        or re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    # Header — proprietor name (left-column label, value usually on next line or same line).
    # Two-column layout often puts the SSN on the same value line, so strip a trailing SSN.
    prop_match = re.search(
        r"Name\s+of\s+proprietor[^\n]*\n+\s*([^\n]+)", text, re.IGNORECASE
    )
    if prop_match:
        candidate = prop_match.group(1).strip()
        candidate = re.sub(r"\s+\d{3}-\d{2}-\d{4}\s*$", "", candidate).strip()
        candidate = re.sub(r"\s+\d{9}\s*$", "", candidate).strip()
        if not re.match(r"^(?:A\s+Principal|Social\s+security)", candidate, re.IGNORECASE):
            data.proprietor_name = candidate[:120]

    ssn_match = re.search(
        r"Name\s+of\s+proprietor[^\n]*\n[^\n]*?(\d{3}-\d{2}-\d{4}|\d{9})",
        text,
        re.IGNORECASE,
    )
    if not ssn_match:
        ssn_match = re.search(
            r"Social\s+security\s+number[^\n]*\n[^\n]*?(\d{3}-\d{2}-\d{4}|\d{9})",
            text,
            re.IGNORECASE,
        )
    if ssn_match:
        raw = ssn_match.group(1)
        data.proprietor_ssn = raw if "-" in raw else f"{raw[:3]}-{raw[3:5]}-{raw[5:]}"

    # Line A — Principal business or profession.
    # Two-column layout often appends the line-B 6-digit code on the same value line.
    a_match = re.search(
        r"\bA\s+Principal\s+business\s+or\s+profession[^\n]*\n+\s*([^\n]+)",
        text,
        re.IGNORECASE,
    )
    if a_match:
        candidate = a_match.group(1).strip()
        candidate = re.sub(r"\s+\d{6}\s*$", "", candidate).strip()
        if not re.match(r"^(?:B\s+Enter|C\s+Business)", candidate, re.IGNORECASE):
            data.line_a_principal_business = candidate[:120]

    # Line B — Business code (6 digits)
    b_match = re.search(
        r"\bB\s+Enter\s+code[^\n]*\n[^\n]*?(\d{6})", text, re.IGNORECASE
    )
    if not b_match:
        b_match = re.search(r"\bB\s+Enter\s+code[^\n]{0,80}(\d{6})", text, re.IGNORECASE)
    if b_match:
        data.line_b_business_code = b_match.group(1)

    # Line C — Business name.
    # Two-column layout often appends the line-D EIN on the same value line.
    c_match = re.search(
        r"\bC\s+Business\s+name[^\n]*\n+\s*([^\n]+)", text, re.IGNORECASE
    )
    if c_match:
        candidate = c_match.group(1).strip()
        candidate = re.sub(r"\s+\d{2}-\d{7}\s*$", "", candidate).strip()
        if not re.match(r"^(?:D\s+Employer|E\s+Business)", candidate, re.IGNORECASE):
            data.line_c_business_name = candidate[:120]

    # Line D — EIN
    d_match = re.search(
        r"\bD\s+Employer\s+ID\s+number[^\n]*\n[^\n]*?(\d{2}-\d{7})",
        text,
        re.IGNORECASE,
    )
    if not d_match:
        d_match = re.search(r"\bD\s+Employer\s+ID\s+number[^\n]{0,80}(\d{2}-\d{7})", text, re.IGNORECASE)
    if d_match:
        data.line_d_ein = d_match.group(1)

    # Line E — Address
    e_match = re.search(
        r"\bE\s+Business\s+address[^\n]*\n+\s*([^\n]+)\n\s*([^\n]+)",
        text,
        re.IGNORECASE,
    )
    if e_match:
        addr = e_match.group(1).strip()
        city_zip = e_match.group(2).strip()
        if not re.match(r"^(?:F\s+Accounting|City)", addr, re.IGNORECASE):
            data.line_e_business_address = addr[:120]
        if not re.match(r"^F\s+Accounting", city_zip, re.IGNORECASE):
            data.line_e_city_state_zip = city_zip[:120]

    # Line F — Accounting method
    data.line_f_accounting_method = _accounting_method(text)

    # Lines G, H, I, J — Y/N or checkbox answers
    data.line_g_material_participation = _yes_no(r"\bG\s+Did\s+you\s+.materially", text)
    data.line_h_started_or_acquired = _checkbox_after(
        r"\bH\s+If\s+you\s+started\s+or\s+acquired", text, window_chars=200
    )
    data.line_i_made_payments_requiring_1099 = _yes_no(
        r"\bI\s+Did\s+you\s+make\s+any\s+payments", text
    )
    data.line_j_filed_required_1099 = _yes_no(
        r"\bJ\s+If\s+.Yes,?.\s+did\s+you", text
    )

    # ===== Part I — Income =====
    data.line_1_gross_receipts = _money_line(r"1\s+Gross\s+receipts\s+or\s+sales", text)
    data.line_1_statutory_employee = bool(
        re.search(r"\.Statutory\s+employee.\s+box[^\n]{0,80}(?:\[X\]|☒|✓|\bX\b)",
                  text, re.IGNORECASE)
    )
    data.line_2_returns_allowances = _money_line(r"2\s+Returns\s+and\s+allowances", text)
    data.line_3_net_receipts = _money_line(r"3\s+Subtract\s+line\s+2\s+from\s+line\s+1", text)
    data.line_4_cogs = _money_line(r"4\s+Cost\s+of\s+goods\s+sold\s+\(from\s+line\s+42\)", text)
    data.line_5_gross_profit = _money_line(r"5\s+Gross\s+profit", text)
    data.line_6_other_income = _money_line(r"6\s+Other\s+income", text)
    data.line_7_gross_income = _money_line(r"7\s+Gross\s+income", text)

    # ===== Part II — Expenses =====
    data.line_8_advertising = _money_line(r"\b8\s+Advertising\b", text)
    data.line_9_car_truck = _money_line(r"\b9\s+Car\s+and\s+truck\s+expenses", text)
    data.line_10_commissions_fees = _money_line(r"\b10\s+Commissions\s+and\s+fees", text)
    data.line_11_contract_labor = _money_line(r"\b11\s+Contract\s+labor", text)
    data.line_12_depletion = _money_line(r"\b12\s+Depletion", text)
    data.line_13_depreciation_section_179 = _money_line(
        r"\b13\s+Depreciation\s+and\s+section\s+179", text
    )
    data.line_14_employee_benefit_programs = _money_line(
        r"\b14\s+Employee\s+benefit\s+programs", text
    )
    data.line_15_insurance = _money_line(r"\b15\s+Insurance", text)
    data.line_16a_mortgage_interest = _money_line(
        r"\b16\s*a\s+Mortgage\s+\(paid\s+to\s+banks", text
    ) or _money_line(r"\b16a\b", text)
    # Line 16b often renders as "b Other 16b VALUE" (subletter-only label,
    # with the line marker on the right); fall back to matching the marker directly.
    data.line_16b_other_interest = _money_line(r"\b16\s*b\s+Other\b", text) \
        or _money_line(r"\b16b\b", text)
    data.line_17_legal_professional = _money_line(
        r"\b17\s+Legal\s+and\s+professional\s+services", text
    )
    data.line_18_office_expense = _money_line(r"\b18\s+Office\s+expense", text)
    data.line_19_pension_profit_sharing = _money_line(
        r"\b19\s+Pension\s+and\s+profit-sharing", text
    )
    data.line_20a_rent_vehicles_machinery = _money_line(
        r"\b20\s*a\s+Vehicles,\s+machinery", text
    ) or _money_line(r"\ba\s+Vehicles,\s+machinery", text) \
        or _money_line(r"\b20a\b", text)
    data.line_20b_rent_other_property = _money_line(
        r"\b20\s*b\s+Other\s+business\s+property", text
    ) or _money_line(r"\bb\s+Other\s+business\s+property", text) \
        or _money_line(r"\b20b\b", text)
    data.line_21_repairs_maintenance = _money_line(r"\b21\s+Repairs\s+and\s+maintenance", text)
    data.line_22_supplies = _money_line(r"\b22\s+Supplies", text)
    data.line_23_taxes_licenses = _money_line(r"\b23\s+Taxes\s+and\s+licenses", text)
    # Lines 24a/b often render as bare subletter ("a Travel", "b Deductible meals")
    # because line 24's heading "Travel and meals:" sits above on its own row.
    data.line_24a_travel = _money_line(r"\b24\s*a\s+Travel\b", text) \
        or _money_line(r"\ba\s+Travel\b[^\n]*?24a", text) \
        or _money_line(r"\b24a\b", text)
    data.line_24b_meals = _money_line(r"\b24\s*b\s+Deductible\s+meals", text) \
        or _money_line(r"\bb\s+Deductible\s+meals", text) \
        or _money_line(r"\b24b\b", text)
    data.line_25_utilities = _money_line(r"\b25\s+Utilities", text)
    data.line_26_wages = _money_line(r"\b26\s+Wages", text)
    data.line_27a_energy_efficient_bldg = _money_line(
        r"\b27\s*a\s+Energy\s+efficient", text
    ) or _money_line(r"\ba\s+Energy\s+efficient", text) \
        or _money_line(r"\b27a\b", text)
    data.line_27b_other_expenses = _money_line(
        r"\b27\s*b\s+Other\s+expenses\s+\(from\s+line\s+48\)", text
    ) or _money_line(r"\bb\s+Other\s+expenses\s+\(from\s+line\s+48\)", text) \
        or _money_line(r"\b27b\b", text)
    data.line_28_total_expenses = _money_line(
        r"\b28\s+Total\s+expenses\s+before\s+expenses\s+for\s+business\s+use", text
    )
    data.line_29_tentative_profit_loss = _money_line(
        r"\b29\s+Tentative\s+profit\s+or\s+\(loss\)", text
    )
    data.line_30_home_office = _money_line(
        r"\b30\s+Expenses\s+for\s+business\s+use\s+of\s+your\s+home", text
    )
    # Simplified-method square footages (unlabelled — captured if present right of "(a)" / "(b)")
    sqft_a = re.search(
        r"\(a\)\s+your\s+home[^\n]{0,40}(\d{1,5})", text, re.IGNORECASE
    )
    if sqft_a:
        data.line_30_simplified_method_total_sqft = float(sqft_a.group(1))
    sqft_b = re.search(
        r"\(b\)\s+the\s+part\s+of\s+your\s+home\s+used\s+for\s+business[^\n]{0,40}(\d{1,5})",
        text,
        re.IGNORECASE,
    )
    if sqft_b:
        data.line_30_simplified_method_business_sqft = float(sqft_b.group(1))

    data.line_31_net_profit_loss = _money_line(
        r"\b31\s+Net\s+profit\s+or\s+\(loss\)", text
    )
    data.line_32a_all_at_risk = _checkbox_after(
        r"32a\s+All\s+investment\s+is\s+at\s+risk", text, window_chars=60
    ) or _checkbox_after(r"All\s+investment\s+is\s+at\s+risk", text, window_chars=40)
    data.line_32b_some_not_at_risk = _checkbox_after(
        r"32b\s+Some\s+investment\s+is\s+not", text, window_chars=60
    ) or _checkbox_after(r"Some\s+investment\s+is\s+not\s+at\s+risk", text, window_chars=40)

    # ===== Part III — Cost of Goods Sold =====
    data.line_33_inventory_method = _inventory_method(text)
    data.line_34_inventory_method_change = _yes_no(
        r"34\s+Was\s+there\s+any\s+change\s+in\s+determining", text
    )
    data.line_35_inventory_beginning = _money_line(r"\b35\s+Inventory\s+at\s+beginning", text)
    data.line_36_purchases = _money_line(r"\b36\s+Purchases", text)
    data.line_37_cost_of_labor = _money_line(r"\b37\s+Cost\s+of\s+labor", text)
    data.line_38_materials_supplies = _money_line(r"\b38\s+Materials\s+and\s+supplies", text)
    data.line_39_other_costs = _money_line(r"\b39\s+Other\s+costs", text)
    data.line_40_total_inputs = _money_line(r"\b40\s+Add\s+lines\s+35\s+through\s+39", text)
    data.line_41_inventory_end = _money_line(r"\b41\s+Inventory\s+at\s+end", text)
    data.line_42_cogs = _money_line(r"\b42\s+Cost\s+of\s+goods\s+sold", text)

    # ===== Part IV — Vehicle =====
    date_match = re.search(
        r"43\s+When\s+did\s+you\s+place\s+your\s+vehicle[^\n]{0,200}?"
        r"(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        data.line_43_date_placed_in_service = re.sub(r"\s+", "", date_match.group(1))

    # Mileage row often spans two lines: "44 ... \n a Business N b Commuting N c Other N"
    miles_match = re.search(
        r"44[\s\S]{0,200}?\ba\s+Business[^\d]{0,40}(\d[\d,]*)"
        r"[\s\S]{0,80}?\bb\s+Commuting[^\d]{0,40}(\d[\d,]*)"
        r"[\s\S]{0,80}?\bc\s+Other[^\d]{0,40}(\d[\d,]*)",
        text,
        re.IGNORECASE,
    )
    if miles_match:
        data.line_44a_business_miles = parse_amount_token(miles_match.group(1))
        data.line_44b_commuting_miles = parse_amount_token(miles_match.group(2))
        data.line_44c_other_miles = parse_amount_token(miles_match.group(3))

    data.line_45_personal_use_offduty = _yes_no(
        r"45\s+Was\s+your\s+vehicle\s+available\s+for\s+personal", text
    )
    data.line_46_another_vehicle_personal = _yes_no(
        r"46\s+Do\s+you\s+\(or\s+your\s+spouse\)\s+have\s+another", text
    )
    data.line_47a_evidence_to_support = _yes_no(
        r"47a\s+Do\s+you\s+have\s+evidence", text
    )
    data.line_47b_evidence_written = _yes_no(
        r"\bb\s+If\s+.Yes,?.\s+is\s+the\s+evidence\s+written", text
    )

    # ===== Part V — Other Expenses =====
    data.other_expenses_items = _parse_other_expenses(text)
    data.line_48_total_other_expenses = _money_line(
        r"\b48\s+Total\s+other\s+expenses", text
    )

    # Confidence — weight the identity + bottom-line fields heavily
    identity = [
        data.proprietor_name,
        data.line_a_principal_business,
        data.line_b_business_code,
        data.line_d_ein,
    ]
    bottom_line = [
        data.line_1_gross_receipts,
        data.line_7_gross_income,
        data.line_28_total_expenses,
        data.line_31_net_profit_loss,
    ]
    populated = sum(1 for f in identity if f not in (None, "")) + sum(
        1 for f in bottom_line if f is not None
    )
    data.confidence = round(min(1.0, populated / 8), 2)

    return data
