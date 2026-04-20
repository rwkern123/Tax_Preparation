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

NOTE ON MERGE CONFLICTS:
  Schedule B shares field-name prefixes (f1_01–f1_64) with Form 1040.
  Schedule D and Form 1040 both use f1_10–f1_43.
  To prevent values leaking across forms when merged, schedule PDFs are filled
  with auto_regenerate=True (bakes in appearance streams), then their AcroForm
  is stripped before merging. Form 1040 retains its interactive AcroForm.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

# 2024 standard deduction amounts
_STD_DEDUCTION = {
    "single":  14600.0,
    "mfj":     29200.0,
    "mfs":     14600.0,
    "hoh":     21900.0,
    "qss":     29200.0,
}

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(value: float | None, sign: bool = False) -> str:
    if value is None:
        return ""
    if sign and value < 0:
        return f"({abs(value):,.0f})"
    return f"{value:,.0f}"


def _fmt_ssn(ssn: str | None) -> str:
    if not ssn:
        return ""
    digits = "".join(c for c in ssn if c.isdigit())
    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return ssn


def _fmt_dob(dob: str | None) -> tuple[str, str, str]:
    """Parse DOB string (YYYY-MM-DD or MM/DD/YYYY) → (mm, dd, yyyy)."""
    if not dob:
        return "", "", ""
    dob = dob.strip()
    if "-" in dob:
        parts = dob.split("-")
        if len(parts) == 3:
            return parts[1], parts[2], parts[0]
    if "/" in dob:
        parts = dob.split("/")
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
    return "", "", ""


# ---------------------------------------------------------------------------
# AcroForm fill helper
# ---------------------------------------------------------------------------

def _fill_acro_pdf(template_path: str, fields_by_page: dict[int, dict[str, str]],
                   generate_appearances: bool = False) -> bytes:
    import pypdf

    reader = pypdf.PdfReader(template_path)
    writer = pypdf.PdfWriter()
    writer.append(reader)

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
                auto_regenerate=generate_appearances,
            )

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _fill_schedule_flat(template_path: str, fields_by_page: dict[int, dict[str, str]]) -> bytes:
    """Fill a schedule PDF with baked-in appearances, then strip AcroForm to prevent merge conflicts."""
    import pypdf

    # Fill with auto-generated appearances so values show without an AcroForm
    pdf_bytes = _fill_acro_pdf(template_path, fields_by_page, generate_appearances=True)

    # Strip AcroForm so the merged result doesn't have field-name collisions
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    writer = pypdf.PdfWriter()
    writer.append(reader)
    root = writer._root_object
    root_obj = root.get_object()
    if "/AcroForm" in root_obj:
        del root_obj[pypdf.generic.NameObject("/AcroForm")]

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
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
# Page 1 header (annotation y positions measured from bottom of page):
#   y≈733  f1_01  Taxpayer first name + MI
#   y≈733  f1_02  Taxpayer last name
#   y≈733  f1_03  Taxpayer SSN (narrow visual field; value still stored)
#   y≈720  f1_04  Spouse first name + MI
#   y≈720  f1_05/06/07  Taxpayer DOB (mm / dd / yyyy)
#   y≈720  f1_08/09/10  Spouse DOB (mm / dd / yyyy)
#   y≈709  f1_11  Spouse last name
#   y≈709  f1_12  Taxpayer SSN (wider field; mirrors f1_03 value)
#   y≈709  f1_13  Spouse SSN
#   y≈684  f1_14  Home address
#   y≈684  f1_15  City
#   y≈684  f1_16  ZIP code
#   y≈722  c1_1   Filing status: Single
#   y≈722  c1_2   Filing status: MFJ
#   y≈722  c1_3   Filing status: MFS
#   y≈710  c1_4   Filing status: HOH
# Page 1 income lines:
#   f1_47  Line 1a  — W-2 wages
#   f1_57  Line 1z  — Total wages
#   f1_59  Line 2b  — Taxable interest
#   f1_60  Line 3a  — Qualified dividends
#   f1_61  Line 3b  — Ordinary dividends
#   f1_70  Line 7   — Capital gain or (loss)
#   f1_72  Line 9   — Total income
#   f1_74  Line 11  — Adjusted gross income
#   f1_75  Line 12  — Standard or itemized deduction
# Page 2:
#   f2_01  SSN repeat
#   f2_12  Line 25a — Federal withholding (W-2)
#   f2_13  Line 25b — Federal withholding (1099)
#   f2_15  Line 25d — Total withholding
#   f2_23  Line 33  — Total payments
#   f2_37  Sign    — Taxpayer occupation
#   f2_38  Sign    — Spouse occupation


def _build_1040_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    lines = {ln["key"]: ln["value"] for ln in agg.get("lines", [])}

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))
    dob_mm, dob_dd, dob_yyyy = _fmt_dob(user.get("dob"))
    address = user.get("address", "")
    city    = user.get("city", "")
    zip_code = user.get("zip", "") or user.get("zip_code", "")

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

    # Line 12: standard deduction vs itemized
    filing_status = user.get("filing_status", "single")
    std_ded = _STD_DEDUCTION.get(filing_status, 14600.0)
    itemized_total = agg.get("sched_a", {}).get("itemized_total") or 0.0
    line_12 = max(std_ded, itemized_total) if agi is not None else None

    page0: dict[str, str] = {
        # Header
        "f1_01[0]": first,
        "f1_02[0]": last,
        "f1_03[0]": ssn,
        # Taxpayer DOB
        "f1_05[0]": dob_mm,
        "f1_06[0]": dob_dd,
        "f1_07[0]": dob_yyyy,
        # Income lines
        "f1_47[0]": _fmt(w2_wages),
        "f1_57[0]": _fmt(w2_wages),
        "f1_59[0]": _fmt(interest),
        "f1_60[0]": _fmt(qual_div),
        "f1_61[0]": _fmt(ord_div),
        "f1_70[0]": _fmt(cap_gain, sign=True),
        "f1_72[0]": _fmt(total_inc),
        "f1_74[0]": _fmt(agi),
        "f1_75[0]": _fmt(line_12),
        # Address
        "f1_14[0]": address,
        "f1_15[0]": city,
        "f1_16[0]": zip_code,
    }

    # Filing status checkbox
    fs_map = {"single": "c1_1[0]", "mfj": "c1_2[0]", "mfs": "c1_3[0]", "hoh": "c1_4[0]"}
    fs_field = fs_map.get(filing_status)
    if fs_field:
        page0[fs_field] = "/Yes"

    # Spouse header (MFJ / MFS)
    if filing_status in ("mfj", "mfs"):
        sp = user.get("spouse", {}) or {}
        sp_first = sp.get("first_name", "")
        sp_last  = sp.get("last_name", "")
        sp_ssn   = _fmt_ssn(sp.get("ssn", ""))
        sp_mm, sp_dd, sp_yyyy = _fmt_dob(sp.get("dob"))
        page0["f1_04[0]"] = sp_first
        page0["f1_11[0]"] = sp_last
        page0["f1_12[0]"] = ssn        # taxpayer SSN (wider field)
        page0["f1_13[0]"] = sp_ssn     # spouse SSN
        page0["f1_08[0]"] = sp_mm
        page0["f1_09[0]"] = sp_dd
        page0["f1_10[0]"] = sp_yyyy
    else:
        # Single filer — use wider SSN field for taxpayer
        page0["f1_12[0]"] = ssn

    page1: dict[str, str] = {
        "f2_01[0]": ssn,
        "f2_12[0]": _fmt(w2_wh),
        "f2_13[0]": _fmt(b_wh),
        "f2_15[0]": _fmt(total_wh),
    }

    # Total payments = withholding (no estimated tax in scope)
    if total_wh is not None:
        page1["f2_23[0]"] = _fmt(total_wh)

    if agg.get("occupation_tp"):
        page1["f2_37[0]"] = agg["occupation_tp"]
    if agg.get("occupation_sp"):
        page1["f2_38[0]"] = agg["occupation_sp"]

    return {0: page0, 1: page1}


# ---------------------------------------------------------------------------
# Schedule A field mappings
# ---------------------------------------------------------------------------
#
# Schedule A (f1040sa.pdf) — form1[0] root:
#   f1_1[0]   Name
#   f1_2[0]   SSN
#   f1_4[0]   Line 2 — AGI (for 7.5% threshold)
#   f1_5[0]   Line 3 — 7.5% of line 2
#   f1_8[0]   Line 5b — Real estate taxes
#   f1_11[0]  Line 5e — Total SALT (5a–5d)
#   f1_14[0]  Line 6  — SALT capped at $10,000
#   f1_15[0]  Line 8a — Mortgage interest from Form 1098
#   f1_19[0]  Line 10 — Total interest (8a + 8b + 9)
#   f1_20[0]  Line 11 — Gifts by cash or check
#   f1_21[0]  Line 12 — Other gifts (noncash)
#   f1_22[0]  Line 14 — Total gifts to charity (11+12+13)
#   f1_27[0]  Line 17 — Total itemized deductions


def _build_scha_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
    sa = agg.get("sched_a", {})

    mortgage_int        = sa.get("mortgage_interest", 0.0) or 0.0
    real_estate_tax     = sa.get("real_estate_taxes", 0.0) or 0.0
    agi                 = sa.get("agi") or 0.0
    charitable_cash     = sa.get("charitable_cash", 0.0) or 0.0
    charitable_noncash  = sa.get("charitable_noncash", 0.0) or 0.0

    salt_uncapped = real_estate_tax
    salt_capped   = min(salt_uncapped, 10000.0) if salt_uncapped else None

    total_interest = mortgage_int or None
    total_charitable = charitable_cash + charitable_noncash or None
    total_itemized = (
        (salt_capped or 0.0) + (mortgage_int or 0.0) + (total_charitable or 0.0)
    ) or None

    first = user.get("first_name", "")
    last  = user.get("last_name", "")
    ssn   = _fmt_ssn(user.get("ssn", ""))

    fields: dict[str, str] = {
        "f1_1[0]":  f"{first} {last}".strip(),
        "f1_2[0]":  ssn,
        "f1_4[0]":  _fmt(agi),
        "f1_5[0]":  _fmt(agi * 0.075 if agi else None),
        "f1_8[0]":  _fmt(real_estate_tax if real_estate_tax else None),
        "f1_11[0]": _fmt(salt_uncapped if salt_uncapped else None),
        "f1_14[0]": _fmt(salt_capped),
        "f1_15[0]": _fmt(mortgage_int if mortgage_int else None),
        "f1_19[0]": _fmt(total_interest),
        "f1_20[0]": _fmt(charitable_cash if charitable_cash else None),
        "f1_21[0]": _fmt(charitable_noncash if charitable_noncash else None),
        "f1_22[0]": _fmt(total_charitable),
        "f1_27[0]": _fmt(total_itemized),
    }

    return {0: fields}


# ---------------------------------------------------------------------------
# Schedule B field mappings
# ---------------------------------------------------------------------------

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
    ("f1_34[0]", "f1_35[0]"),
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

    int_total = 0.0
    for i, entry in enumerate(interest_entries[:len(_SCHB_INT_ROWS)]):
        name_f, amt_f = _SCHB_INT_ROWS[i]
        amt = entry.get("amount") or 0.0
        fields[name_f] = entry.get("name", "")
        fields[amt_f]  = _fmt(amt)
        int_total += amt

    if interest_entries:
        fields["f1_31[0]"] = _fmt(int_total)
        fields["f1_33[0]"] = _fmt(int_total)

    div_total = 0.0
    for i, entry in enumerate(dividend_entries[:len(_SCHB_DIV_ROWS)]):
        name_f, amt_f = _SCHB_DIV_ROWS[i]
        amt = entry.get("amount") or 0.0
        fields[name_f] = entry.get("name", "")
        fields[amt_f]  = _fmt(amt)
        div_total += amt

    if dividend_entries:
        fields["f1_64[0]"] = _fmt(div_total)

    return {0: fields}


# ---------------------------------------------------------------------------
# Schedule D field mappings
# ---------------------------------------------------------------------------

def _build_schd_fields(agg: dict, user: dict) -> dict[int, dict[str, str]]:
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

    if st_proceeds is not None or st_basis is not None:
        page0["f1_3[0]"]  = _fmt(st_proceeds)
        page0["f1_4[0]"]  = _fmt(st_basis)
        page0["f1_5[0]"]  = _fmt(st_washed, sign=True)
        page0["f1_6[0]"]  = _fmt(st_gain,  sign=True)
        page0["f1_22[0]"] = _fmt(st_gain,  sign=True)

    if lt_proceeds is not None or lt_basis is not None:
        page0["f1_23[0]"] = _fmt(lt_proceeds)
        page0["f1_24[0]"] = _fmt(lt_basis)
        page0["f1_25[0]"] = _fmt(lt_washed, sign=True)
        page0["f1_26[0]"] = _fmt(lt_gain,  sign=True)
        page0["f1_43[0]"] = _fmt(lt_gain,  sign=True)

    page1: dict[str, str] = {
        "f2_1[0]": _fmt(total_gain, sign=True),
    }

    return {0: page0, 1: page1}


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate_1040_data(parsed_docs: list[dict], user: dict, year: int,
                        manual_entries: list[dict] | None = None) -> dict:
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

    int_entries:  list[dict] = []
    div_entries:  list[dict] = []

    has_any = False
    occ_tp = occ_sp = None

    for doc in parsed_docs:
        ej   = doc.get("extracted_json") or {}
        name = doc.get("original_name", "unknown")

        for w2 in ej.get("w2", []):
            v1 = w2.get("box1_wages")
            v2 = w2.get("box2_fed_withholding")
            if v1 is not None:
                w2_wages   += float(v1); has_any = True
            if v2 is not None:
                w2_withheld += float(v2); has_any = True
            if (v1 is not None or v2 is not None) and name not in w2_sources:
                w2_sources.append(name)

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

            bs = b.get("b_summary") or {}
            st = bs.get("short_term_gain_loss")
            lt = bs.get("long_term_gain_loss")
            if st is not None:
                cap_gain += float(st); has_any = True
                st_gl     = (st_gl or 0.0) + float(st)
            if lt is not None:
                cap_gain += float(lt); has_any = True
                lt_gl     = (lt_gl or 0.0) + float(lt)

        for b in ej.get("brokerage_1099", []):
            bs = b.get("b_summary") or {}
            if bs.get("proceeds") is not None:
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

        for trade in ej.get("brokerage_1099_trades", []):
            fw = trade.get("federal_income_tax_withheld")
            if fw is not None:
                b_withheld += float(fw); has_any = True
                if name not in b1099_sources:
                    b1099_sources.append(name)

        for f in ej.get("form_1098", []):
            vm = f.get("mortgage_interest_received")
            vr = f.get("real_estate_taxes")
            if vm is not None:
                mortgage_int    += float(vm); has_any = True
            if vr is not None:
                real_estate_tax += float(vr); has_any = True
            if (vm is not None or vr is not None) and name not in f1098_sources:
                f1098_sources.append(name)

        for py in ej.get("prior_year_return", []):
            if not occ_tp and py.get("taxpayer_occupation"):
                occ_tp = py["taxpayer_occupation"]
            if not occ_sp and py.get("spouse_occupation"):
                occ_sp = py["spouse_occupation"]

    # Manual entries (charitable contributions etc.)
    charitable_cash    = 0.0
    charitable_noncash = 0.0
    charitable_sources: list[str] = []
    for entry in (manual_entries or []):
        cat = entry.get("category", "")
        amt = float(entry.get("amount") or 0)
        if cat == "charitable_cash":
            charitable_cash += amt
            has_any = True
        elif cat == "charitable_noncash":
            charitable_noncash += amt
            has_any = True
        if amt > 0 and "Manual entry" not in charitable_sources:
            charitable_sources.append("Manual entry")

    if not has_any:
        return {}

    total_withheld = w2_withheld + b_withheld
    total_income   = w2_wages + interest + ord_dividends + cap_gain
    agi            = total_income

    salt_capped   = min(real_estate_tax, 10000.0) if real_estate_tax else 0.0
    total_charitable = charitable_cash + charitable_noncash
    itemized_total = salt_capped + mortgage_int + total_charitable
    has_sched_a   = mortgage_int > 0 or real_estate_tax > 0 or total_charitable > 0

    has_sched_b = bool(int_entries or div_entries)
    has_sched_d = (st_gl is not None or lt_gl is not None)
    total_gain_loss = (st_gl or 0.0) + (lt_gl or 0.0) if has_sched_d else None

    lines = [
        {"key": "line_1a",  "label": "1a — W-2 wages, salaries, tips",        "value": w2_wages if w2_sources else None,         "sources": w2_sources,    "sched": None},
        {"key": "line_1z",  "label": "1z — Total wages",                       "value": w2_wages if w2_sources else None,         "sources": w2_sources,    "sched": None},
        {"key": "line_2b",  "label": "2b — Taxable interest",                  "value": interest if b1099_sources else None,      "sources": b1099_sources, "sched": None},
        {"key": "line_3a",  "label": "3a — Qualified dividends",               "value": qual_dividends if b1099_sources else None,"sources": b1099_sources, "sched": None},
        {"key": "line_3b",  "label": "3b — Ordinary dividends",                "value": ord_dividends if b1099_sources else None, "sources": b1099_sources, "sched": None},
        {"key": "line_7",   "label": "7 — Capital gain or (loss)",             "value": cap_gain if b1099_sources else None,      "sources": b1099_sources, "sched": None},
        {"key": "line_9",   "label": "9 — Total income",                       "value": total_income if has_any else None,        "sources": w2_sources + [s for s in b1099_sources if s not in w2_sources], "sched": None},
        {"key": "line_11",  "label": "11 — Adjusted gross income",             "value": agi if has_any else None,                 "sources": [],            "sched": None},
        {"key": "line_25a", "label": "25a — Federal income tax withheld (W-2)","value": w2_withheld if w2_sources else None,      "sources": w2_sources,    "sched": None},
        {"key": "line_25b", "label": "25b — Federal income tax withheld (1099)","value": b_withheld if b1099_sources else None,   "sources": b1099_sources, "sched": None},
        {"key": "line_25d", "label": "25d — Total federal income tax withheld", "value": total_withheld if (w2_sources or b1099_sources) else None, "sources": w2_sources + [s for s in b1099_sources if s not in w2_sources], "sched": None},
        {"key": "scha_8a",  "label": "Sched A 8a — Home mortgage interest",    "value": mortgage_int if f1098_sources else None,  "sources": f1098_sources, "sched": "A"},
        {"key": "scha_5b",  "label": "Sched A 5b — Real estate taxes",         "value": real_estate_tax if f1098_sources else None,"sources": f1098_sources,"sched": "A"},
        {"key": "scha_11",  "label": "Sched A 11 — Charitable (cash)",         "value": charitable_cash if charitable_cash else None,     "sources": charitable_sources, "sched": "A"},
        {"key": "scha_12",  "label": "Sched A 12 — Charitable (noncash)",      "value": charitable_noncash if charitable_noncash else None,"sources": charitable_sources, "sched": "A"},
    ]

    return {
        "lines": lines,
        "has_sched_a": has_sched_a,
        "has_sched_b": has_sched_b,
        "has_sched_d": has_sched_d,
        "occupation_tp": occ_tp,
        "occupation_sp": occ_sp,
        "sched_a": {
            "agi":               agi,
            "mortgage_interest":  mortgage_int if f1098_sources else None,
            "real_estate_taxes":  real_estate_tax if f1098_sources else None,
            "salt_capped":        salt_capped if f1098_sources else None,
            "itemized_total":     itemized_total if has_sched_a else None,
            "charitable_cash":    charitable_cash if charitable_cash else None,
            "charitable_noncash": charitable_noncash if charitable_noncash else None,
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
    try:
        return _do_fill(data, pdf_forms_dir)
    except Exception:
        blank = Path(pdf_forms_dir) / "f1040.pdf"
        if blank.exists():
            return blank.read_bytes()
        return b""


def _do_fill(data: dict, pdf_forms_dir: str) -> bytes:
    forms_dir = Path(pdf_forms_dir)
    user = data.get("_user", {})

    all_pdfs: list[bytes] = []

    # Form 1040 — keep interactive AcroForm
    f1040_path = str(forms_dir / "f1040.pdf")
    f1040_fields = _build_1040_fields(data, user)
    all_pdfs.append(_fill_acro_pdf(f1040_path, f1040_fields, generate_appearances=False))

    # Schedules — flatten (bake appearances, strip AcroForm) to prevent field-name conflicts
    if data.get("has_sched_a"):
        scha_path = str(forms_dir / "f1040sa.pdf")
        if Path(scha_path).exists():
            scha_fields = _build_scha_fields(data, user)
            all_pdfs.append(_fill_schedule_flat(scha_path, scha_fields))

    if data.get("has_sched_b"):
        schb_path = str(forms_dir / "f1040sb.pdf")
        if Path(schb_path).exists():
            schb_fields = _build_schb_fields(data, user)
            all_pdfs.append(_fill_schedule_flat(schb_path, schb_fields))

    if data.get("has_sched_d"):
        schd_path = str(forms_dir / "f1040sd.pdf")
        if Path(schd_path).exists():
            schd_fields = _build_schd_fields(data, user)
            all_pdfs.append(_fill_schedule_flat(schd_path, schd_fields))

    if len(all_pdfs) == 1:
        return all_pdfs[0]
    return _merge_pdfs(all_pdfs)
