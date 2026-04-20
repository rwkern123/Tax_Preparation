"""
Form 1040 filler — fills IRS AcroForm PDFs with extracted tax data.

Generates Form 1040 + applicable schedules (A, B, D), then merges into one PDF.
All field names are derived from inspecting the IRS PDF AcroForm widget annotations.

Field-name reference (terminal /T value → line):
  Form 1040 Page 1: f1_01–f1_75, checkboxes c1_1–c1_n
  Form 1040 Page 2: f2_01–f2_50, checkboxes c2_1–c2_n
  Schedule A      : f1_1–f1_30   (form1[0] root)
  Schedule B      : f1_01–f1_66  (topmostSubform root)
  Schedule D      : f1_1–f1_43, f2_1–f2_4
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(value: float | None, sign: bool = False) -> str:
    """Format a dollar value as comma-separated integer string."""
    if value is None:
        return ""
    if sign and value < 0:
        return f"({abs(value):,.0f})"
    return f"{value:,.0f}"


def _fmt_ssn(ssn: str | None) -> str:
    """Normalize SSN to XXX-XX-XXXX format."""
    if not ssn:
        return ""
    digits = "".join(c for c in ssn if c.isdigit())
    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return ssn


# ---------------------------------------------------------------------------
# AcroForm fill helper
# ---------------------------------------------------------------------------

def _fill_acro_pdf(template_path: str, fields_by_page: dict[int, dict[str, str]]) -> bytes:
    """
    Fill a fillable PDF using its AcroForm fields.

    Args:
        template_path: Path to the blank IRS PDF template.
        fields_by_page: {page_index: {field_terminal_name: value_string}}

    Returns:
        PDF bytes with fields filled.
    """
    import pypdf

    reader = pypdf.PdfReader(template_path)
    writer = pypdf.PdfWriter()
    writer.append(reader)

    # Signal to PDF viewers to regenerate appearances from field values
    acroform = writer._root_object.get("/AcroForm")
    if acroform:
        acroform_obj = acroform.get_object()
        acroform_obj.update({
            pypdf.generic.NameObject("/NeedAppearances"): pypdf.generic.BooleanObject(True)
        })

    for page_idx, fields in fields_by_page.items():
        if page_idx < len(writer.pages):
            writer.update_page_form_field_values(
                writer.pages[page_idx],
                {k: v for k, v in fields.items() if v},
                auto_regenerate=False,
            )

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Merge multiple PDF byte strings into one."""
    import pypdf

    writer = pypdf.PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        writer.append(reader)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Form 1040 field mappings
# ---------------------------------------------------------------------------
#
# All keys below are the terminal /T field names as they appear in the PDF.
# Two pages: page index 0 = Page 1, page index 1 = Page 2.
#
# Line mapping (2024 Form 1040):
#   Page 1
#     f1_01  Header — Taxpayer first name + MI
#     f1_02  Header — Taxpayer last name
#     f1_03  Header — Taxpayer SSN
#     f1_04  Header — Spouse first name + MI (MFJ)
#     f1_47  Line 1a  — W-2 wages
#     f1_57  Line 1z  — Total wages
#     f1_58  Line 2a  — Tax-exempt interest
#     f1_59  Line 2b  — Taxable interest
#     f1_60  Line 3a  — Qualified dividends
#     f1_61  Line 3b  — Ordinary dividends
#     f1_62  Line 4a  — Total IRA distributions
#     f1_63  Line 4b  — Taxable IRA
#     f1_65  Line 5a  — Total pensions/annuities
#     f1_66  Line 5b  — Taxable pensions
#     f1_68  Line 6a  — Total social security
#     f1_69  Line 6b  — Taxable social security
#     f1_70  Line 7   — Capital gain or (loss)
#     f1_71  Line 8   — Other income (Schedule 1, line 10)
#     f1_72  Line 9   — Total income
#     f1_73  Line 10  — Adjustments (Schedule 1, line 26)
#     f1_74  Line 11  — Adjusted gross income
#     f1_75  Line 12  — Standard or itemized deduction
#   Page 2
#     f2_01  Header — SSN repeat
#     f2_02  Line 16  — Income tax
#     f2_03  Line 17  — AMT (Schedule 2, line 1)
#     f2_04  Line 18  — Add lines 16 + 17
#     f2_05  Line 19  — Child tax credit
#     f2_06  Line 20  — Schedule 3, line 8
#     f2_08  Line 21  — Add lines 19 + 20
#     f2_09  Line 22  — Tax after credits
#     f2_10  Line 23  — Other taxes (Schedule 2, line 21)
#     f2_11  Line 24  — Total tax
#     f2_12  Line 25a — Federal withholding (W-2)
#     f2_13  Line 25b — Federal withholding (1099)
#     f2_14  Line 25c — Other withholding
#     f2_15  Line 25d — Total withholding
#     f2_16  Line 26  — Estimated tax payments
#     f2_23  Line 33  — Total payments
#     f2_24  Line 34  — Overpayment
#     f2_25  Line 35a — Amount refunded
#     f2_29  Line 37  — Amount owed
#     f2_30  Line 38  — Estimated tax penalty
#     f2_37  Sign — Taxpayer occupation
#     f2_38  Sign — Spouse occupation


def _build_1040_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    """Build field dicts for Form 1040 pages 0 and 1."""
    lines = {ln["key"]: ln["value"] for ln in agg.get("lines", [])}

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))

    # Computed totals
    w2_wages   = lines.get("line_1a")
    interest   = lines.get("line_2b")
    ord_div    = lines.get("line_3b")
    qual_div   = lines.get("line_3a")
    cap_gain   = lines.get("line_7")
    total_inc  = lines.get("line_9")
    agi        = lines.get("line_11")
    w2_wh      = lines.get("line_25a")
    b_wh       = lines.get("line_25b")
    total_wh   = lines.get("line_25d")

    page0: dict[str, str] = {
        # Header
        "f1_01[0]": first,
        "f1_02[0]": last,
        "f1_03[0]": ssn,
        # Income lines
        "f1_47[0]": _fmt(w2_wages),          # Line 1a — W-2 wages
        "f1_57[0]": _fmt(w2_wages),          # Line 1z — total wages (= 1a if no other)
        "f1_59[0]": _fmt(interest),           # Line 2b — taxable interest
        "f1_60[0]": _fmt(qual_div),           # Line 3a — qualified dividends
        "f1_61[0]": _fmt(ord_div),            # Line 3b — ordinary dividends
        "f1_70[0]": _fmt(cap_gain, sign=True),# Line 7  — capital gain/(loss)
        "f1_72[0]": _fmt(total_inc),          # Line 9  — total income
        "f1_74[0]": _fmt(agi),                # Line 11 — AGI
    }

    # Spouse header (MFJ)
    filing_status = user.get("filing_status", "single")
    if filing_status in ("mfj", "mfs"):
        sp = user.get("spouse", {}) or {}
        page0["f1_04[0]"] = sp.get("first_name", "")

    page1: dict[str, str] = {
        "f2_01[0]": ssn,          # SSN repeat at top of page 2
        "f2_12[0]": _fmt(w2_wh),  # Line 25a — W-2 withholding
        "f2_13[0]": _fmt(b_wh),   # Line 25b — 1099 withholding
        "f2_15[0]": _fmt(total_wh),# Line 25d — total withholding
    }

    # Refund / owed (simple: no credits or other taxes)
    if total_wh is not None:
        tax = 0.0  # We don't compute estimated tax here; leave line 24 blank
        if agg.get("occupation_tp"):
            page1["f2_37[0]"] = agg["occupation_tp"]
        if agg.get("occupation_sp"):
            page1["f2_38[0]"] = agg["occupation_sp"]

    return {0: page0, 1: page1}


# ---------------------------------------------------------------------------
# Schedule A field mappings
# ---------------------------------------------------------------------------
#
# Schedule A (f1040sa.pdf) field layout — form1[0] root:
#   f1_3[0]   Line 1   — Medical expenses
#   f1_4[0]   Line 2   — AGI (for 7.5% threshold)
#   f1_5[0]   Line 3   — 7.5% of line 2
#   f1_6[0]   Line 4   — Medical deduction (1 - 3, if positive)
#   f1_7[0]   Line 5a  — State/local income taxes
#   f1_8[0]   Line 5b  — Real estate taxes
#   f1_9[0]   Line 5c  — Personal property taxes
#   f1_10[0]  Line 5d  — Other state taxes
#   f1_11[0]  Line 5e  — Total SALT (5a–5d)
#   f1_13[0]  Line 6   — Other taxes (amount)
#   f1_14[0]  Line 7   — Total taxes paid (capped at $10,000)
#   f1_15[0]  Line 8a  — Mortgage interest from Form 1098
#   f1_17[0]  Line 8b  — Mortgage interest not on 1098 (amount)
#   f1_18[0]  Line 9   — Investment interest
#   f1_19[0]  Line 10  — Total interest (8a + 8b + 9)
#   f1_20[0]  Line 11  — Gifts by cash or check
#   f1_21[0]  Line 12  — Other gifts (noncash)
#   f1_22[0]  Line 14  — Total gifts to charity (11+12+13)
#   f1_27[0]  Line 17  — Total itemized deductions


def _build_scha_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    """Build Schedule A field dict."""
    sa = agg.get("sched_a", {})

    mortgage_int    = sa.get("mortgage_interest", 0.0) or 0.0
    real_estate_tax = sa.get("real_estate_taxes", 0.0) or 0.0
    agi             = sa.get("agi") or 0.0

    salt_uncapped = real_estate_tax   # we only have real estate taxes
    salt_capped   = min(salt_uncapped, 10000.0) if salt_uncapped else None

    total_interest = mortgage_int or None
    total_itemized = (
        (salt_capped or 0.0) + (mortgage_int or 0.0)
    ) or None

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))

    fields: dict[str, str] = {
        "f1_1[0]":  f"{first} {last}".strip(),
        "f1_2[0]":  ssn,
        "f1_4[0]":  _fmt(agi),                        # Line 2 — AGI
        "f1_5[0]":  _fmt(agi * 0.075 if agi else None),# Line 3 — 7.5% of AGI
        "f1_8[0]":  _fmt(real_estate_tax if real_estate_tax else None),  # Line 5b
        "f1_11[0]": _fmt(salt_uncapped if salt_uncapped else None),       # Line 5e
        "f1_14[0]": _fmt(salt_capped),                                    # Line 7
        "f1_15[0]": _fmt(mortgage_int if mortgage_int else None),         # Line 8a
        "f1_19[0]": _fmt(total_interest),                                 # Line 10
        "f1_27[0]": _fmt(total_itemized),                                 # Line 17 total
    }

    return {0: fields}


# ---------------------------------------------------------------------------
# Schedule B field mappings
# ---------------------------------------------------------------------------
#
# Schedule B (f1040sb.pdf) — topmostSubform root:
#   f1_01[0]  Header name
#   f1_02[0]  Header SSN
#   Part I — Interest:
#     Row 1–14: pairs (name at x=130, amount at x=490)
#       f1_03/f1_04, f1_05/f1_06 … f1_29/f1_30
#     f1_31[0]  Line 1 total (sum of amounts)
#     f1_32[0]  Line 3 (excludable interest — usually 0)
#     f1_33[0]  Line 4 (taxable interest = line 1 - line 3)
#   Part II — Dividends:
#     Row 1: f1_34 (x=202 name), f1_35 (x=490 amount)
#     Row 2–15: f1_36/f1_37, f1_38/f1_39 … f1_62/f1_63
#     f1_64[0]  Line 6 (total ordinary dividends)

_SCHB_INT_ROWS = [
    ("f1_03[0]", "f1_04[0]"),
    ("f1_05[0]", "f1_06[0]"),
    ("f1_07[0]", "f1_08[0]"),
    ("f1_09[0]", "f1_10[0]"),
    ("f1_11[0]", "f1_12[0]"),
    ("f1_13[0]", "f1_14[0]"),
    ("f1_15[0]", "f1_16[0]"),
    ("f1_17[0]", "f1_18[0]"),
    ("f1_19[0]", "f1_20[0]"),
    ("f1_21[0]", "f1_22[0]"),
    ("f1_23[0]", "f1_24[0]"),
    ("f1_25[0]", "f1_26[0]"),
    ("f1_27[0]", "f1_28[0]"),
    ("f1_29[0]", "f1_30[0]"),
]

_SCHB_DIV_ROWS = [
    ("f1_34[0]", "f1_35[0]"),  # row 1 name field is wider (x=202)
    ("f1_36[0]", "f1_37[0]"),
    ("f1_38[0]", "f1_39[0]"),
    ("f1_40[0]", "f1_41[0]"),
    ("f1_42[0]", "f1_43[0]"),
    ("f1_44[0]", "f1_45[0]"),
    ("f1_46[0]", "f1_47[0]"),
    ("f1_48[0]", "f1_49[0]"),
    ("f1_50[0]", "f1_51[0]"),
    ("f1_52[0]", "f1_53[0]"),
    ("f1_54[0]", "f1_55[0]"),
    ("f1_56[0]", "f1_57[0]"),
    ("f1_58[0]", "f1_59[0]"),
    ("f1_60[0]", "f1_61[0]"),
    ("f1_62[0]", "f1_63[0]"),
]


def _build_schb_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    """Build Schedule B field dict."""
    sb = agg.get("sched_b", {})
    interest_entries: list[dict] = sb.get("interest_entries", [])
    dividend_entries: list[dict] = sb.get("dividend_entries", [])

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))

    fields: dict[str, str] = {
        "f1_01[0]": f"{first} {last}".strip(),
        "f1_02[0]": ssn,
    }

    # Interest rows (up to 14 payers)
    int_total = 0.0
    for i, entry in enumerate(interest_entries[:len(_SCHB_INT_ROWS)]):
        name_f, amt_f = _SCHB_INT_ROWS[i]
        amt = entry.get("amount") or 0.0
        fields[name_f] = entry.get("name", "")
        fields[amt_f]  = _fmt(amt)
        int_total += amt

    if interest_entries:
        fields["f1_31[0]"] = _fmt(int_total)   # Line 1 total
        fields["f1_33[0]"] = _fmt(int_total)   # Line 4 taxable (no exclusion)

    # Dividend rows (up to 15 payers)
    div_total = 0.0
    for i, entry in enumerate(dividend_entries[:len(_SCHB_DIV_ROWS)]):
        name_f, amt_f = _SCHB_DIV_ROWS[i]
        amt = entry.get("amount") or 0.0
        fields[name_f] = entry.get("name", "")
        fields[amt_f]  = _fmt(amt)
        div_total += amt

    if dividend_entries:
        fields["f1_64[0]"] = _fmt(div_total)   # Line 6 total ordinary dividends

    return {0: fields}


# ---------------------------------------------------------------------------
# Schedule D field mappings
# ---------------------------------------------------------------------------
#
# Schedule D (f1040sd.pdf) — topmostSubform root:
#   Page 1:
#     f1_1[0]   Header name
#     f1_2[0]   Header SSN
#     Part I — Short-term:
#       Row 1a (cols: proceeds, cost, adjust, gain/loss): f1_3–f1_6
#       Row 1b: f1_7–f1_10
#       Row 2:  f1_11–f1_14
#       Row 3:  f1_15–f1_18
#       f1_19[0]  Line 4 — Gain from installment sales
#       f1_20[0]  Line 5 — Net ST capital loss carryover
#       f1_21[0]  Line 6 — Short-term from partnerships/etc
#       f1_22[0]  Line 7 — Net ST capital gain/(loss) total
#     Part II — Long-term:
#       Row 8a: f1_23–f1_26
#       Row 8b: f1_27–f1_30
#       Row 9:  f1_31–f1_34
#       Row 10: f1_35–f1_38
#       f1_39[0]  Line 11 — Gain from installment sales (LT)
#       f1_40[0]  Line 12 — Capital gain distributions
#       f1_41[0]  Line 13 — LT capital loss carryover
#       f1_42[0]  Line 14 — LT from partnerships/etc
#       f1_43[0]  Line 15 — Net LT capital gain/(loss) total
#   Page 2:
#       f2_1[0]   Line 16 — Combined net capital gain/(loss)


def _build_schd_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    """Build Schedule D field dict."""
    sd = agg.get("sched_d", {})

    st_proceeds = sd.get("st_proceeds")
    st_basis    = sd.get("st_basis")
    st_washed   = sd.get("st_wash_sales")
    st_gain     = sd.get("st_gain_loss")

    lt_proceeds = sd.get("lt_proceeds")
    lt_basis    = sd.get("lt_basis")
    lt_washed   = sd.get("lt_wash_sales")
    lt_gain     = sd.get("lt_gain_loss")

    total_gain  = sd.get("total_gain_loss")

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))

    page0: dict[str, str] = {
        "f1_1[0]": f"{first} {last}".strip(),
        "f1_2[0]": ssn,
    }

    # Part I Row 1a — short-term covered (columns: proceeds, cost, adjustments, gain/loss)
    if st_proceeds is not None or st_basis is not None:
        page0["f1_3[0]"]  = _fmt(st_proceeds)          # Col (d) Proceeds
        page0["f1_4[0]"]  = _fmt(st_basis)             # Col (e) Cost
        page0["f1_5[0]"]  = _fmt(st_washed, sign=True) # Col (g) Wash sale adj
        page0["f1_6[0]"]  = _fmt(st_gain,  sign=True)  # Col (h) Gain/(Loss)
        page0["f1_22[0]"] = _fmt(st_gain,  sign=True)  # Line 7 — net ST total

    # Part II Row 8a — long-term covered
    if lt_proceeds is not None or lt_basis is not None:
        page0["f1_23[0]"] = _fmt(lt_proceeds)          # Col (d) Proceeds
        page0["f1_24[0]"] = _fmt(lt_basis)             # Col (e) Cost
        page0["f1_25[0]"] = _fmt(lt_washed, sign=True) # Col (g) Wash sale adj
        page0["f1_26[0]"] = _fmt(lt_gain,  sign=True)  # Col (h) Gain/(Loss)
        page0["f1_43[0]"] = _fmt(lt_gain,  sign=True)  # Line 15 — net LT total

    page1: dict[str, str] = {
        "f2_1[0]": _fmt(total_gain, sign=True),         # Line 16 — combined total
    }

    return {0: page0, 1: page1}


# ---------------------------------------------------------------------------
# Data aggregation (called by views.py and client_detail template)
# ---------------------------------------------------------------------------

def aggregate_1040_data(parsed_docs: list[dict], user: dict, year: int) -> dict:
    """
    Aggregate extracted fields across all parsed documents into Form 1040 line values.

    Returns a dict with:
      "lines"      : list of line dicts for the UI worksheet
      "sched_a"    : Schedule A input data
      "sched_b"    : Schedule B input data (interest/dividend entries)
      "sched_d"    : Schedule D input data
      "has_sched_a": bool
      "has_sched_b": bool
      "has_sched_d": bool
      "occupation_tp" / "occupation_sp": strings
    """
    w2_wages        = 0.0
    w2_withheld     = 0.0
    interest        = 0.0
    ord_dividends   = 0.0
    qual_dividends  = 0.0
    cap_gain        = 0.0
    b_withheld      = 0.0
    mortgage_int    = 0.0
    real_estate_tax = 0.0
    st_proceeds = st_basis = st_wash = st_gl = None
    lt_proceeds = lt_basis = lt_wash = lt_gl = None

    w2_sources:     list[str] = []
    b1099_sources:  list[str] = []
    f1098_sources:  list[str] = []

    # For Schedule B detail
    int_entries:  list[dict] = []
    div_entries:  list[dict] = []

    has_any = False

    # Prior-year occupations (best effort)
    occ_tp = occ_sp = None

    for doc in parsed_docs:
        ej   = doc.get("extracted_json") or {}
        name = doc.get("original_name", "unknown")

        # W-2 -----------------------------------------------------------------
        for w2 in ej.get("w2", []):
            v1 = w2.get("box1_wages")
            v2 = w2.get("box2_fed_withholding")
            if v1 is not None:
                w2_wages   += float(v1); has_any = True
            if v2 is not None:
                w2_withheld += float(v2); has_any = True
            if (v1 is not None or v2 is not None) and name not in w2_sources:
                w2_sources.append(name)

        # Brokerage 1099 summary ----------------------------------------------
        for b in ej.get("brokerage_1099", []):
            broker = b.get("broker_name") or name
            vi  = b.get("int_interest_income")
            vod = b.get("div_ordinary")
            vqd = b.get("div_qualified")
            if vi  is not None:
                interest      += float(vi);  has_any = True
                int_entries.append({"name": broker, "amount": float(vi)})
            if vod is not None:
                ord_dividends += float(vod); has_any = True
                div_entries.append({"name": broker, "amount": float(vod)})
            if vqd is not None:
                qual_dividends += float(vqd); has_any = True
            if any(x is not None for x in [vi, vod, vqd]) and name not in b1099_sources:
                b1099_sources.append(name)

            # Capital gains from summary
            bs = b.get("b_summary") or {}
            st = bs.get("short_term_gain_loss")
            lt = bs.get("long_term_gain_loss")
            st_proc = bs.get("proceeds")        if bs.get("short_term_gain_loss") is not None else None
            lt_proc = bs.get("proceeds")        if bs.get("long_term_gain_loss")  is not None else None
            st_cost = bs.get("cost_basis")      if bs.get("short_term_gain_loss") is not None else None
            lt_cost = bs.get("cost_basis")      if bs.get("long_term_gain_loss")  is not None else None
            st_ws   = bs.get("wash_sales")
            lt_ws   = bs.get("wash_sales")

            if st is not None:
                cap_gain += float(st); has_any = True
                st_gl     = (st_gl or 0.0) + float(st)
                if bs.get("proceeds") is not None:
                    st_proceeds = (st_proceeds or 0.0) + float(bs["proceeds"]) * (
                        abs(float(st)) / (abs(float(st)) + abs(float(bs.get("long_term_gain_loss") or 0)) + 0.01)
                    )
            if lt is not None:
                cap_gain += float(lt); has_any = True
                lt_gl     = (lt_gl or 0.0) + float(lt)

        # Brokerage proceeds / basis / wash — from b_summary aggregate
        for b in ej.get("brokerage_1099", []):
            bs = b.get("b_summary") or {}
            if bs.get("proceeds") is not None:
                # Split proceeds/basis proportionally between ST and LT if possible
                st_frac = lt_frac = 0.5
                st_g = bs.get("short_term_gain_loss")
                lt_g = bs.get("long_term_gain_loss")
                if st_g is not None and lt_g is not None:
                    total_abs = abs(float(st_g)) + abs(float(lt_g))
                    if total_abs > 0:
                        st_frac = abs(float(st_g)) / total_abs
                        lt_frac = 1.0 - st_frac
                elif st_g is not None:
                    st_frac, lt_frac = 1.0, 0.0
                elif lt_g is not None:
                    st_frac, lt_frac = 0.0, 1.0

                proc = float(bs["proceeds"])
                cost = float(bs["cost_basis"]) if bs.get("cost_basis") is not None else None
                ws   = float(bs["wash_sales"])  if bs.get("wash_sales")  is not None else None

                if st_frac > 0:
                    st_proceeds = (st_proceeds or 0.0) + proc * st_frac
                    if cost is not None:
                        st_basis = (st_basis or 0.0) + cost * st_frac
                    if ws is not None:
                        st_wash  = (st_wash  or 0.0) + ws * st_frac
                if lt_frac > 0:
                    lt_proceeds = (lt_proceeds or 0.0) + proc * lt_frac
                    if cost is not None:
                        lt_basis = (lt_basis or 0.0) + cost * lt_frac
                    if ws is not None:
                        lt_wash  = (lt_wash  or 0.0) + ws * lt_frac

        # Trade-level federal withholding
        for trade in ej.get("brokerage_1099_trades", []):
            fw = trade.get("federal_income_tax_withheld")
            if fw is not None:
                b_withheld += float(fw); has_any = True
                if name not in b1099_sources:
                    b1099_sources.append(name)

        # Form 1098 -----------------------------------------------------------
        for f in ej.get("form_1098", []):
            vm = f.get("mortgage_interest_received")
            vr = f.get("real_estate_taxes")
            if vm is not None:
                mortgage_int    += float(vm); has_any = True
            if vr is not None:
                real_estate_tax += float(vr); has_any = True
            if (vm is not None or vr is not None) and name not in f1098_sources:
                f1098_sources.append(name)

        # Prior year return — for occupations
        for py in ej.get("prior_year_return", []):
            if not occ_tp and py.get("taxpayer_occupation"):
                occ_tp = py["taxpayer_occupation"]
            if not occ_sp and py.get("spouse_occupation"):
                occ_sp = py["spouse_occupation"]

    if not has_any:
        return {}

    total_withheld = w2_withheld + b_withheld
    total_income   = w2_wages + interest + ord_dividends + cap_gain
    agi            = total_income  # simplified (no adjustments in scope)

    # Schedule A check
    salt_capped   = min(real_estate_tax, 10000.0) if real_estate_tax else 0.0
    itemized_total = salt_capped + mortgage_int
    has_sched_a   = mortgage_int > 0 or real_estate_tax > 0

    # Schedule B check (required if interest > $1,500 or dividends > $1,500, but we always show if data exists)
    has_sched_b = bool(int_entries or div_entries)

    # Schedule D check
    has_sched_d = (st_gl is not None or lt_gl is not None)
    total_gain_loss = (st_gl or 0.0) + (lt_gl or 0.0) if has_sched_d else None

    # UI worksheet lines (matches template expectations)
    lines = [
        {
            "key": "line_1a",
            "label": "1a — W-2 wages, salaries, tips",
            "value": w2_wages if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key": "line_1z",
            "label": "1z — Total wages",
            "value": w2_wages if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key": "line_2b",
            "label": "2b — Taxable interest",
            "value": interest if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key": "line_3a",
            "label": "3a — Qualified dividends",
            "value": qual_dividends if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key": "line_3b",
            "label": "3b — Ordinary dividends",
            "value": ord_dividends if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key": "line_7",
            "label": "7 — Capital gain or (loss)",
            "value": cap_gain if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key": "line_9",
            "label": "9 — Total income",
            "value": total_income if has_any else None,
            "sources": w2_sources + [s for s in b1099_sources if s not in w2_sources],
            "sched": None,
        },
        {
            "key": "line_11",
            "label": "11 — Adjusted gross income",
            "value": agi if has_any else None,
            "sources": [],
            "sched": None,
        },
        {
            "key": "line_25a",
            "label": "25a — Federal income tax withheld (W-2)",
            "value": w2_withheld if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key": "line_25b",
            "label": "25b — Federal income tax withheld (1099)",
            "value": b_withheld if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key": "line_25d",
            "label": "25d — Total federal income tax withheld",
            "value": total_withheld if (w2_sources or b1099_sources) else None,
            "sources": w2_sources + [s for s in b1099_sources if s not in w2_sources],
            "sched": None,
        },
        {
            "key": "scha_8a",
            "label": "Sched A 8a — Home mortgage interest",
            "value": mortgage_int if f1098_sources else None,
            "sources": f1098_sources,
            "sched": "A",
        },
        {
            "key": "scha_5b",
            "label": "Sched A 5b — Real estate taxes",
            "value": real_estate_tax if f1098_sources else None,
            "sources": f1098_sources,
            "sched": "A",
        },
    ]

    return {
        "lines": lines,
        "has_sched_a": has_sched_a,
        "has_sched_b": has_sched_b,
        "has_sched_d": has_sched_d,
        "occupation_tp": occ_tp,
        "occupation_sp": occ_sp,
        "sched_a": {
            "agi":              agi,
            "mortgage_interest": mortgage_int if f1098_sources else None,
            "real_estate_taxes": real_estate_tax if f1098_sources else None,
            "salt_capped":      salt_capped if f1098_sources else None,
            "itemized_total":   itemized_total if has_sched_a else None,
        },
        "sched_b": {
            "interest_entries": int_entries,
            "dividend_entries": div_entries,
            "total_interest":   interest if int_entries else None,
            "total_dividends":  ord_dividends if div_entries else None,
        },
        "sched_d": {
            "st_proceeds":    st_proceeds,
            "st_basis":       st_basis,
            "st_wash_sales":  st_wash,
            "st_gain_loss":   st_gl,
            "lt_proceeds":    lt_proceeds,
            "lt_basis":       lt_basis,
            "lt_wash_sales":  lt_wash,
            "lt_gain_loss":   lt_gl,
            "total_gain_loss": total_gain_loss,
        },
    }


# ---------------------------------------------------------------------------
# PDF generation entry point
# ---------------------------------------------------------------------------

def fill_1040_pdf(data: dict, pdf_forms_dir: str) -> bytes:
    """
    Generate a filled Form 1040 packet (1040 + applicable schedules).

    Args:
        data: dict returned by aggregate_1040_data()
        pdf_forms_dir: directory containing f1040.pdf, f1040sa.pdf, etc.

    Returns:
        Merged PDF bytes. Falls back to blank Form 1040 on any error.
    """
    try:
        return _do_fill(data, pdf_forms_dir)
    except Exception:
        # Fall back to blank Form 1040
        blank = Path(pdf_forms_dir) / "f1040.pdf"
        if blank.exists():
            return blank.read_bytes()
        return b""


def _do_fill(data: dict, pdf_forms_dir: str) -> bytes:
    forms_dir = Path(pdf_forms_dir)
    user = data.get("_user", {})

    all_pdfs: list[bytes] = []

    # --- Form 1040 ---
    f1040_path = str(forms_dir / "f1040.pdf")
    f1040_fields = _build_1040_fields(data, user)
    all_pdfs.append(_fill_acro_pdf(f1040_path, f1040_fields))

    # --- Schedule A (mortgage interest / real estate taxes) ---
    if data.get("has_sched_a"):
        scha_path = str(forms_dir / "f1040sa.pdf")
        if Path(scha_path).exists():
            scha_fields = _build_scha_fields(data, user)
            all_pdfs.append(_fill_acro_pdf(scha_path, scha_fields))

    # --- Schedule B (interest and dividends detail) ---
    if data.get("has_sched_b"):
        schb_path = str(forms_dir / "f1040sb.pdf")
        if Path(schb_path).exists():
            schb_fields = _build_schb_fields(data, user)
            all_pdfs.append(_fill_acro_pdf(schb_path, schb_fields))

    # --- Schedule D (capital gains / losses) ---
    if data.get("has_sched_d"):
        schd_path = str(forms_dir / "f1040sd.pdf")
        if Path(schd_path).exists():
            schd_fields = _build_schd_fields(data, user)
            all_pdfs.append(_fill_acro_pdf(schd_path, schd_fields))

    if len(all_pdfs) == 1:
        return all_pdfs[0]
    return _merge_pdfs(all_pdfs)
