"""
Federal income tax estimator.
Supports tax years 2024 and 2025 using IRS Publication 17 / Rev. Proc. 2024-40 figures.
This is an estimate only — a licensed tax professional must review all returns.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.models import ExtractionResult


# ---------------------------------------------------------------------------
# Tax constants by year
# ---------------------------------------------------------------------------

_CONSTANTS: Dict[int, Dict] = {
    2024: {
        "standard_deductions": {
            "single": 14_600.0,
            "mfj":    29_200.0,
            "mfs":    14_600.0,
            "hoh":    21_900.0,
            "qss":    29_200.0,
        },
        "brackets": {
            "single": [
                (0,       0.10), (11_600,  0.12), (47_150,  0.22),
                (100_525, 0.24), (191_950, 0.32), (243_725, 0.35), (609_350, 0.37),
            ],
            "mfj": [
                (0,       0.10), (23_200,  0.12), (94_300,  0.22),
                (201_050, 0.24), (383_900, 0.32), (487_450, 0.35), (731_200, 0.37),
            ],
            "mfs": [
                (0,       0.10), (11_600,  0.12), (47_150,  0.22),
                (100_525, 0.24), (191_950, 0.32), (243_725, 0.35), (365_600, 0.37),
            ],
            "hoh": [
                (0,       0.10), (16_550,  0.12), (63_100,  0.22),
                (100_500, 0.24), (191_950, 0.32), (243_700, 0.35), (609_350, 0.37),
            ],
            "qss": [
                (0,       0.10), (23_200,  0.12), (94_300,  0.22),
                (201_050, 0.24), (383_900, 0.32), (487_450, 0.35), (731_200, 0.37),
            ],
        },
        # 0% LTCG top, 15% LTCG top
        "ltcg_thresholds": {
            "single": (47_025.0, 518_900.0),
            "mfj":    (94_050.0, 583_750.0),
            "mfs":    (47_025.0, 291_850.0),
            "hoh":    (63_000.0, 551_350.0),
            "qss":    (94_050.0, 583_750.0),
        },
        "salt_cap": {
            "single": 10_000.0, "mfj": 10_000.0,
            "mfs": 5_000.0, "hoh": 10_000.0, "qss": 10_000.0,
        },
        "ctc_phase_out": {
            "single": 200_000.0, "mfj": 400_000.0,
            "mfs": 200_000.0, "hoh": 200_000.0, "qss": 400_000.0,
        },
        "niit_threshold": {
            "single": 200_000.0, "mfj": 250_000.0,
            "mfs": 125_000.0, "hoh": 200_000.0, "qss": 250_000.0,
        },
        "se_ss_wage_base": 168_600.0,
        "ctc_per_child": 2_000.0,
    },
    2025: {
        "standard_deductions": {
            "single": 15_000.0,
            "mfj":    30_000.0,
            "mfs":    15_000.0,
            "hoh":    22_500.0,
            "qss":    30_000.0,
        },
        "brackets": {
            "single": [
                (0,       0.10), (11_925,  0.12), (48_475,  0.22),
                (103_350, 0.24), (197_300, 0.32), (250_525, 0.35), (626_350, 0.37),
            ],
            "mfj": [
                (0,       0.10), (23_850,  0.12), (96_950,  0.22),
                (206_700, 0.24), (394_600, 0.32), (501_050, 0.35), (751_600, 0.37),
            ],
            "mfs": [
                (0,       0.10), (11_925,  0.12), (48_475,  0.22),
                (103_350, 0.24), (197_300, 0.32), (250_525, 0.35), (375_800, 0.37),
            ],
            "hoh": [
                (0,       0.10), (17_000,  0.12), (64_850,  0.22),
                (103_350, 0.24), (197_300, 0.32), (250_500, 0.35), (626_350, 0.37),
            ],
            "qss": [
                (0,       0.10), (23_850,  0.12), (96_950,  0.22),
                (206_700, 0.24), (394_600, 0.32), (501_050, 0.35), (751_600, 0.37),
            ],
        },
        # IRS Rev. Proc. 2024-40 LTCG thresholds
        "ltcg_thresholds": {
            "single": (48_350.0, 533_400.0),
            "mfj":    (96_700.0, 600_050.0),
            "mfs":    (48_350.0, 300_000.0),
            "hoh":    (64_750.0, 566_700.0),
            "qss":    (96_700.0, 600_050.0),
        },
        # 2025 increased SALT cap per TCJA extension legislation
        "salt_cap": {
            "single": 40_000.0, "mfj": 40_000.0,
            "mfs": 20_000.0, "hoh": 40_000.0, "qss": 40_000.0,
        },
        "ctc_phase_out": {
            "single": 200_000.0, "mfj": 400_000.0,
            "mfs": 200_000.0, "hoh": 200_000.0, "qss": 400_000.0,
        },
        "niit_threshold": {
            "single": 200_000.0, "mfj": 250_000.0,
            "mfs": 125_000.0, "hoh": 200_000.0, "qss": 250_000.0,
        },
        "se_ss_wage_base": 176_100.0,
        "ctc_per_child": 2_000.0,
    },
}

# SS benefit taxability thresholds (Pub. 915) — unchanged year-to-year
_SS_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "single": (25_000.0, 34_000.0),
    "mfj":    (32_000.0, 44_000.0),
    "mfs":    (0.0, 0.0),   # MFS: 85% of SS always taxable
    "hoh":    (25_000.0, 34_000.0),
    "qss":    (32_000.0, 44_000.0),
}

_FILING_STATUS_LABELS = {
    "single": "Single",
    "mfj":    "Married Filing Jointly",
    "mfs":    "Married Filing Separately",
    "hoh":    "Head of Household",
    "qss":    "Qualifying Surviving Spouse",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TaxEstimate:
    filing_status: str = "single"
    tax_year: int = 2025

    # Income items
    w2_wages: float = 0.0
    taxable_interest: float = 0.0
    ordinary_dividends: float = 0.0
    qualified_dividends: float = 0.0
    short_term_cap_gains: float = 0.0
    long_term_cap_gains: float = 0.0
    ira_pension_taxable: float = 0.0
    ss_benefits_gross: float = 0.0
    ss_benefits_taxable: float = 0.0
    schedule_c_net: float = 0.0
    unemployment_comp: float = 0.0
    other_income: float = 0.0
    total_income: float = 0.0

    # Above-the-line deductions
    se_tax_deduction: float = 0.0
    other_adjustments: float = 0.0
    agi: float = 0.0

    # Deductions
    standard_deduction: float = 0.0
    itemized_deduction: float = 0.0
    deduction_used: float = 0.0
    deduction_type: str = "standard"   # "standard" | "itemized"
    qbi_deduction: float = 0.0
    taxable_income: float = 0.0

    # Tax computation
    ordinary_income_for_brackets: float = 0.0
    preferred_income: float = 0.0
    regular_tax: float = 0.0
    ltcg_tax: float = 0.0
    niit: float = 0.0
    se_tax: float = 0.0
    total_tax_before_credits: float = 0.0

    # Credits
    child_tax_credit: float = 0.0
    foreign_tax_credit: float = 0.0
    total_credits: float = 0.0

    # Total federal income tax
    total_tax: float = 0.0

    # Payments
    w2_withholding: float = 0.0
    other_withholding: float = 0.0
    estimated_payments: float = 0.0
    total_payments: float = 0.0

    # Result: positive = refund, negative = amount owed
    refund_or_owed: float = 0.0

    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _get_constants(year: int) -> Dict:
    return _CONSTANTS.get(year, _CONSTANTS[2025])


def _compute_bracket_tax(income: float, brackets: list) -> float:
    tax = 0.0
    for i, (threshold, rate) in enumerate(brackets):
        if income <= threshold:
            break
        next_threshold = brackets[i + 1][0] if i + 1 < len(brackets) else float("inf")
        taxable_in_bracket = min(income, next_threshold) - threshold
        tax += taxable_in_bracket * rate
    return tax


def _compute_ltcg_tax(
    ordinary_income: float,
    preferred_income: float,
    zero_top: float,
    fifteen_top: float,
) -> float:
    """Stack preferred income on top of ordinary income and apply 0/15/20% bands."""
    if preferred_income <= 0:
        return 0.0

    tax = 0.0
    base = ordinary_income
    remaining = preferred_income

    zero_available = max(0.0, zero_top - base)
    zero_used = min(remaining, zero_available)
    remaining -= zero_used
    base += zero_used

    if remaining <= 0:
        return 0.0

    fifteen_available = max(0.0, fifteen_top - base)
    fifteen_used = min(remaining, fifteen_available)
    tax += fifteen_used * 0.15
    remaining -= fifteen_used

    tax += remaining * 0.20
    return tax


def _compute_ss_taxable(
    agi_before_ss: float,
    ss_gross: float,
    filing_status: str,
) -> float:
    if ss_gross <= 0:
        return 0.0
    if filing_status == "mfs":
        return ss_gross * 0.85

    low, high = _SS_THRESHOLDS.get(filing_status, (25_000.0, 34_000.0))
    combined = agi_before_ss + ss_gross * 0.50

    if combined <= low:
        return 0.0
    elif combined <= high:
        return min(ss_gross * 0.50, (combined - low) * 0.50)
    else:
        base_50 = (high - low) * 0.50
        extra = (combined - high) * 0.85
        return min(ss_gross * 0.85, base_50 + extra)


def _compute_se_tax(net_se_income: float, ss_wage_base: float) -> Tuple[float, float]:
    """Return (se_tax, se_deduction). Deduction is 50% of SE tax."""
    if net_se_income <= 0:
        return 0.0, 0.0
    se_wages = net_se_income * 0.9235
    ss_tax = min(se_wages, ss_wage_base) * 0.124
    medicare_tax = se_wages * 0.029
    se_tax = ss_tax + medicare_tax
    return se_tax, se_tax * 0.50


# ---------------------------------------------------------------------------
# Main calculation function
# ---------------------------------------------------------------------------

def calculate_tax(
    result: ExtractionResult,
    filing_status: str = "single",
    num_children: int = 0,
    estimated_payments: float = 0.0,
    foreign_tax_credit: float = 0.0,
    tax_year: int = 2025,
) -> TaxEstimate:
    """
    Compute a federal income tax estimate from extracted document data.
    Returns a TaxEstimate with all intermediate line items.
    """
    fs = filing_status.lower().strip()
    if fs not in _CONSTANTS[2025]["standard_deductions"]:
        fs = "single"

    c = _get_constants(tax_year)
    est = TaxEstimate(filing_status=fs, tax_year=tax_year)
    notes: List[str] = []

    # -------------------------------------------------------------------
    # 1. Aggregate income from all extracted documents
    # -------------------------------------------------------------------

    for w2 in result.w2:
        est.w2_wages += w2.box1_wages or 0.0
        est.w2_withholding += w2.box2_fed_withholding or 0.0

    for b in result.brokerage_1099:
        est.ordinary_dividends += b.div_ordinary or 0.0
        est.qualified_dividends += b.div_qualified or 0.0
        est.taxable_interest += b.int_interest_income or 0.0
        est.short_term_cap_gains += (b.b_short_term_covered or 0.0) + (b.b_short_term_noncovered or 0.0)
        est.long_term_cap_gains += (b.b_long_term_covered or 0.0) + (b.b_long_term_noncovered or 0.0)
        # Section 1256: 40% short-term / 60% long-term
        sec1256 = b.section_1256_net_gain_loss or 0.0
        if sec1256 != 0.0:
            est.short_term_cap_gains += sec1256 * 0.40
            est.long_term_cap_gains += sec1256 * 0.60

    nec_comp = sum(f.box1_nonemployee_compensation or 0.0 for f in result.form_1099_nec)
    est.other_withholding += sum(f.box4_fed_withholding or 0.0 for f in result.form_1099_nec)

    # Schedule C net profit flows to SE income; NEC goes to Schedule C if present, else standalone
    if result.schedule_c:
        est.schedule_c_net = sum(c_item.line_31_net_profit_loss or 0.0 for c_item in result.schedule_c)
        if nec_comp:
            notes.append(
                f"1099-NEC income (${nec_comp:,.0f}) should be reported on Schedule C. "
                "Verify it is included in Schedule C gross receipts."
            )
    else:
        est.schedule_c_net = nec_comp

    for r in result.form_1099_r:
        if r.box2a_taxable_amount is not None:
            taxable = r.box2a_taxable_amount
        else:
            taxable = r.box1_gross_distribution or 0.0
            if r.box2b_taxable_not_determined:
                notes.append(
                    f"1099-R from {r.payer_name or 'unknown'}: taxable amount not determined — "
                    "using gross distribution as conservative estimate."
                )
        est.ira_pension_taxable += taxable
        est.other_withholding += r.box4_fed_withholding or 0.0

    for ssa in result.ssa_1099:
        est.ss_benefits_gross += ssa.box5_net_benefits or 0.0
        est.other_withholding += ssa.box6_voluntary_tax_withheld or 0.0

    for g in result.form_1099_g:
        est.unemployment_comp += g.box1_unemployment_compensation or 0.0
        est.other_withholding += g.box4_fed_withholding or 0.0

    for m in result.form_1099_misc:
        est.other_income += (m.box1_rents or 0.0) + (m.box2_royalties or 0.0) + (m.box3_other_income or 0.0)
        est.other_withholding += m.box4_fed_withholding or 0.0

    # -------------------------------------------------------------------
    # 2. SE tax (needed before AGI for the half-SE deduction)
    # -------------------------------------------------------------------
    se_tax, se_deduction = _compute_se_tax(est.schedule_c_net, c["se_ss_wage_base"])
    est.se_tax = se_tax
    est.se_tax_deduction = se_deduction

    # -------------------------------------------------------------------
    # 3. Taxable SS benefits (Pub. 915) — needs pre-SS AGI
    # -------------------------------------------------------------------
    agi_before_ss = (
        est.w2_wages
        + est.taxable_interest
        + est.ordinary_dividends
        + est.short_term_cap_gains
        + est.long_term_cap_gains
        + est.ira_pension_taxable
        + est.schedule_c_net
        + est.unemployment_comp
        + est.other_income
        - est.se_tax_deduction
        - est.other_adjustments
    )
    est.ss_benefits_taxable = _compute_ss_taxable(agi_before_ss, est.ss_benefits_gross, fs)

    if est.ss_benefits_gross > 0:
        pct = (est.ss_benefits_taxable / est.ss_benefits_gross * 100) if est.ss_benefits_gross else 0
        notes.append(
            f"Social Security: ${est.ss_benefits_gross:,.0f} gross; "
            f"${est.ss_benefits_taxable:,.0f} ({pct:.0f}%) estimated as taxable."
        )

    # -------------------------------------------------------------------
    # 4. Total income and AGI
    # -------------------------------------------------------------------
    est.total_income = (
        est.w2_wages
        + est.taxable_interest
        + est.ordinary_dividends
        + est.short_term_cap_gains
        + est.long_term_cap_gains
        + est.ira_pension_taxable
        + est.ss_benefits_taxable
        + est.schedule_c_net
        + est.unemployment_comp
        + est.other_income
    )
    est.agi = max(0.0, est.total_income - est.se_tax_deduction - est.other_adjustments)

    # -------------------------------------------------------------------
    # 5. Deductions (standard vs. itemized)
    # -------------------------------------------------------------------
    std_ded = c["standard_deductions"][fs]
    est.standard_deduction = std_ded

    mortgage_interest = sum(f.mortgage_interest_received or 0.0 for f in result.form_1098)
    real_estate_taxes = sum(f.real_estate_taxes or 0.0 for f in result.form_1098)
    state_taxes = sum(w2.box17_state_tax or 0.0 for w2 in result.w2)
    salt_raw = state_taxes + real_estate_taxes
    salt = min(salt_raw, c["salt_cap"][fs])
    est.itemized_deduction = mortgage_interest + salt

    if est.itemized_deduction > std_ded:
        est.deduction_used = est.itemized_deduction
        est.deduction_type = "itemized"
        notes.append(
            f"Using itemized deductions (${est.itemized_deduction:,.0f}) vs. "
            f"standard deduction (${std_ded:,.0f}). "
            "Add charitable contributions and other items to verify."
        )
        if salt_raw > c["salt_cap"][fs]:
            notes.append(
                f"SALT capped at ${c['salt_cap'][fs]:,.0f} "
                f"(actual SALT was ${salt_raw:,.0f})."
            )
    else:
        est.deduction_used = std_ded
        est.deduction_type = "standard"

    # QBI deduction — simplified 20% of positive SE/business income
    if est.schedule_c_net > 0:
        taxable_before_qbi = max(0.0, est.agi - est.deduction_used)
        # Limited to 20% of (taxable income minus preferred income)
        qbi_limit = max(0.0, taxable_before_qbi - (est.qualified_dividends + max(0.0, est.long_term_cap_gains))) * 0.20
        est.qbi_deduction = min(est.schedule_c_net * 0.20, qbi_limit)
        notes.append(
            f"Section 199A QBI deduction estimated at ${est.qbi_deduction:,.0f} "
            "(simplified 20% of business income, subject to taxable income limit). "
            "May be further limited by W-2 wages, UBIA, or SSTB rules."
        )

    est.taxable_income = max(0.0, est.agi - est.deduction_used - est.qbi_deduction)

    # -------------------------------------------------------------------
    # 6. Tax computation
    # -------------------------------------------------------------------
    ltcg_thresholds = c["ltcg_thresholds"][fs]
    net_ltcg = max(0.0, est.long_term_cap_gains)
    est.preferred_income = min(est.qualified_dividends + net_ltcg, est.taxable_income)
    est.ordinary_income_for_brackets = max(0.0, est.taxable_income - est.preferred_income)

    est.regular_tax = _compute_bracket_tax(est.ordinary_income_for_brackets, c["brackets"][fs])
    est.ltcg_tax = _compute_ltcg_tax(
        est.ordinary_income_for_brackets,
        est.preferred_income,
        ltcg_thresholds[0],
        ltcg_thresholds[1],
    )

    # Net Investment Income Tax (3.8%)
    niit_threshold = c["niit_threshold"][fs]
    if est.agi > niit_threshold:
        net_inv_income = (
            est.taxable_interest
            + est.ordinary_dividends
            + est.long_term_cap_gains
            + est.short_term_cap_gains
            + sum(f.box1_rents or 0.0 for f in result.form_1099_misc)
        )
        niit_base = min(max(0.0, net_inv_income), est.agi - niit_threshold)
        est.niit = niit_base * 0.038
        if est.niit > 0:
            notes.append(f"Net Investment Income Tax: ${est.niit:,.0f} (3.8% on ${niit_base:,.0f}).")

    est.total_tax_before_credits = est.regular_tax + est.ltcg_tax + est.niit + est.se_tax

    # -------------------------------------------------------------------
    # 7. Credits
    # -------------------------------------------------------------------
    if num_children > 0:
        ctc_max = num_children * c["ctc_per_child"]
        phase_out_start = c["ctc_phase_out"][fs]
        excess = max(0.0, est.agi - phase_out_start)
        phase_out = (excess // 1_000) * 50.0
        est.child_tax_credit = min(max(0.0, ctc_max - phase_out), est.total_tax_before_credits)

    est.foreign_tax_credit = min(
        foreign_tax_credit,
        max(0.0, est.total_tax_before_credits - est.child_tax_credit),
    )
    est.total_credits = est.child_tax_credit + est.foreign_tax_credit
    est.total_tax = max(0.0, est.total_tax_before_credits - est.total_credits)

    # -------------------------------------------------------------------
    # 8. Payments and refund/balance due
    # -------------------------------------------------------------------
    est.estimated_payments = estimated_payments
    est.total_payments = est.w2_withholding + est.other_withholding + est.estimated_payments
    est.refund_or_owed = est.total_payments - est.total_tax

    # -------------------------------------------------------------------
    # 9. Final notes
    # -------------------------------------------------------------------
    if est.refund_or_owed >= 0:
        notes.append(f"Estimated REFUND: ${est.refund_or_owed:,.0f}.")
    else:
        notes.append(f"Estimated AMOUNT OWED: ${abs(est.refund_or_owed):,.0f}.")

    notes.insert(0, (
        f"ESTIMATE ONLY for tax year {tax_year} "
        f"({_FILING_STATUS_LABELS.get(fs, fs)}). "
        "Based on extracted document data — a licensed tax professional must verify all figures before filing."
    ))
    est.notes = notes
    return est


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    if v < 0:
        return f"(${abs(v):>12,.2f})"
    return f" ${v:>12,.2f} "


def tax_estimate_to_markdown(est: TaxEstimate, client: str = "") -> str:
    fs_label = _FILING_STATUS_LABELS.get(est.filing_status, est.filing_status)
    header = f"# Federal Income Tax Estimate — {est.tax_year}"
    if client:
        header += f"\n**Client:** {client}"
    header += f"\n**Filing Status:** {fs_label}"

    def row(label: str, value: float, indent: int = 0) -> str:
        pad = "  " * indent
        return f"| {pad}{label:<45} | {_fmt(value)} |"

    lines = [
        header,
        "",
        "| Line Item                                         |      Amount      |",
        "|---------------------------------------------------|------------------|",
        "| **INCOME**                                        |                  |",
        row("W-2 wages", est.w2_wages, 1),
        row("Taxable interest", est.taxable_interest, 1),
        row("Ordinary dividends", est.ordinary_dividends, 1),
        row("Short-term capital gains", est.short_term_cap_gains, 1),
        row("Long-term capital gains", est.long_term_cap_gains, 1),
        row("IRA / pension taxable distributions", est.ira_pension_taxable, 1),
        row("Social Security taxable (est.)", est.ss_benefits_taxable, 1),
        row("Schedule C / SE net income", est.schedule_c_net, 1),
        row("Unemployment compensation", est.unemployment_comp, 1),
        row("Other income", est.other_income, 1),
        row("**Total Income**", est.total_income),
        "| **ADJUSTMENTS (above-the-line)**                  |                  |",
        row("SE tax deduction (50% of SE tax)", -est.se_tax_deduction, 1),
        row("Other adjustments", -est.other_adjustments, 1),
        row("**Adjusted Gross Income (AGI)**", est.agi),
        "| **DEDUCTIONS**                                    |                  |",
        row(f"Deduction used ({est.deduction_type})", -est.deduction_used, 1),
        row("QBI deduction (Sec. 199A, simplified)", -est.qbi_deduction, 1),
        row("**Taxable Income**", est.taxable_income),
        "| **TAX COMPUTATION**                               |                  |",
        row("Ordinary income tax (bracket method)", est.regular_tax, 1),
        row("Tax on LTCG / qualified dividends", est.ltcg_tax, 1),
        row("Net Investment Income Tax (3.8%)", est.niit, 1),
        row("Self-employment tax", est.se_tax, 1),
        row("**Total Tax Before Credits**", est.total_tax_before_credits),
        "| **CREDITS**                                       |                  |",
        row("Child Tax Credit", -est.child_tax_credit, 1),
        row("Foreign Tax Credit", -est.foreign_tax_credit, 1),
        row("**Total Federal Income Tax**", est.total_tax),
        "| **PAYMENTS**                                      |                  |",
        row("W-2 federal withholding", -est.w2_withholding, 1),
        row("Other withholding (1099s, etc.)", -est.other_withholding, 1),
        row("Estimated tax payments", -est.estimated_payments, 1),
        row("**Total Payments**", est.total_payments),
        "|---------------------------------------------------|------------------|",
    ]

    if est.refund_or_owed >= 0:
        lines.append(row(f"**ESTIMATED REFUND**", est.refund_or_owed))
    else:
        lines.append(row(f"**ESTIMATED AMOUNT OWED**", abs(est.refund_or_owed)))

    lines += [
        "",
        "---",
        "## Notes",
    ]
    for note in est.notes:
        lines.append(f"- {note}")

    lines += [
        "",
        "---",
        "*This estimate is based solely on documents extracted by the Tax Preparation workflow. "
        "It does not account for items not yet received (K-1s, etc.), carryforwards, AMT, "
        "or credits beyond those listed above. A licensed tax professional must review all returns.*",
    ]
    return "\n".join(lines)


def write_tax_estimate(
    out_dir: Path,
    est: TaxEstimate,
    client: str = "",
) -> None:
    """Write Tax_Estimate.json and Tax_Estimate.md to out_dir."""
    data = asdict(est)
    (out_dir / "Tax_Estimate.json").write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )
    md = tax_estimate_to_markdown(est, client=client)
    (out_dir / "Tax_Estimate.md").write_text(md, encoding="utf-8")


def calculate_tax_from_docs(
    parsed_docs: List[Dict],
    filing_status: str = "single",
    num_children: int = 0,
    estimated_payments: float = 0.0,
    foreign_tax_credit: float = 0.0,
    tax_year: int = 2025,
    manual_entries: Optional[List[Dict]] = None,
) -> TaxEstimate:
    """
    Compute a tax estimate directly from the preparer app's parsed_docs format
    (list of dicts each containing an 'extracted_json' key).
    This is the entry point used by the preparer web UI.
    """
    from src.models import (
        ExtractionResult, W2Data, Brokerage1099Data, Form1098Data,
        Form1099NECData, Form1099RData, FormSSA1099Data, ScheduleCData,
        Form1099GData, Form1099MISCData,
    )

    result = ExtractionResult()

    for doc in parsed_docs:
        ej = doc.get("extracted_json") or {}

        for w in ej.get("w2", []):
            result.w2.append(W2Data(
                box1_wages=_f(w.get("box1_wages")),
                box2_fed_withholding=_f(w.get("box2_fed_withholding")),
                box17_state_tax=_f(w.get("box17_state_tax")),
            ))

        for b in ej.get("brokerage_1099", []):
            bs = b.get("b_summary") or {}
            result.brokerage_1099.append(Brokerage1099Data(
                broker_name=b.get("broker_name"),
                div_ordinary=_f(b.get("div_ordinary")),
                div_qualified=_f(b.get("div_qualified")),
                int_interest_income=_f(b.get("int_interest_income")),
                section_1256_net_gain_loss=_f(b.get("section_1256_net_gain_loss")),
                b_short_term_covered=_f(bs.get("short_term_covered") or b.get("b_short_term_covered")),
                b_short_term_noncovered=_f(bs.get("short_term_noncovered") or b.get("b_short_term_noncovered")),
                b_long_term_covered=_f(bs.get("long_term_covered") or b.get("b_long_term_covered")),
                b_long_term_noncovered=_f(bs.get("long_term_noncovered") or b.get("b_long_term_noncovered")),
            ))
            # Also pick up net gain/loss from b_summary if individual covered/noncovered not present
            st_gl = _f(bs.get("short_term_gain_loss"))
            lt_gl = _f(bs.get("long_term_gain_loss"))
            if st_gl is not None and result.brokerage_1099[-1].b_short_term_covered is None:
                result.brokerage_1099[-1] = Brokerage1099Data(
                    broker_name=result.brokerage_1099[-1].broker_name,
                    div_ordinary=result.brokerage_1099[-1].div_ordinary,
                    div_qualified=result.brokerage_1099[-1].div_qualified,
                    int_interest_income=result.brokerage_1099[-1].int_interest_income,
                    section_1256_net_gain_loss=result.brokerage_1099[-1].section_1256_net_gain_loss,
                    b_short_term_covered=st_gl,
                    b_long_term_covered=lt_gl,
                )

        for f in ej.get("form_1098", []):
            result.form_1098.append(Form1098Data(
                lender_name=f.get("lender_name"),
                mortgage_interest_received=_f(f.get("mortgage_interest_received")),
                real_estate_taxes=_f(f.get("real_estate_taxes")),
            ))

        for n in ej.get("form_1099_nec", []):
            result.form_1099_nec.append(Form1099NECData(
                payer_name=n.get("payer_name"),
                box1_nonemployee_compensation=_f(n.get("box1_nonemployee_compensation")),
                box4_fed_withholding=_f(n.get("box4_fed_withholding")),
            ))

        for r in ej.get("form_1099_r", []):
            result.form_1099_r.append(Form1099RData(
                payer_name=r.get("payer_name"),
                box1_gross_distribution=_f(r.get("box1_gross_distribution")),
                box2a_taxable_amount=_f(r.get("box2a_taxable_amount")),
                box2b_taxable_not_determined=bool(r.get("box2b_taxable_not_determined")),
                box4_fed_withholding=_f(r.get("box4_fed_withholding")),
            ))

        for s in ej.get("ssa_1099", []):
            result.ssa_1099.append(FormSSA1099Data(
                box5_net_benefits=_f(s.get("box5_net_benefits")),
                box6_voluntary_tax_withheld=_f(s.get("box6_voluntary_tax_withheld")),
            ))

        for sc in ej.get("schedule_c", []):
            result.schedule_c.append(ScheduleCData(
                line_c_business_name=sc.get("line_c_business_name"),
                line_31_net_profit_loss=_f(sc.get("line_31_net_profit_loss")),
            ))

        for g in ej.get("form_1099_g", []):
            result.form_1099_g.append(Form1099GData(
                box1_unemployment_compensation=_f(g.get("box1_unemployment_compensation")),
                box4_fed_withholding=_f(g.get("box4_fed_withholding")),
            ))

        for m in ej.get("form_1099_misc", []):
            result.form_1099_misc.append(Form1099MISCData(
                box1_rents=_f(m.get("box1_rents")),
                box2_royalties=_f(m.get("box2_royalties")),
                box3_other_income=_f(m.get("box3_other_income")),
                box4_fed_withholding=_f(m.get("box4_fed_withholding")),
            ))

    # Inject manual charitable entries so itemized deduction is accurate
    charitable_cash = sum(
        float(e.get("amount") or 0)
        for e in (manual_entries or [])
        if e.get("category") == "charitable_cash"
    )
    charitable_noncash = sum(
        float(e.get("amount") or 0)
        for e in (manual_entries or [])
        if e.get("category") == "charitable_noncash"
    )

    est = calculate_tax(
        result,
        filing_status=filing_status,
        num_children=num_children,
        estimated_payments=estimated_payments,
        foreign_tax_credit=foreign_tax_credit,
        tax_year=tax_year,
    )

    # Recalculate itemized with charitable contributions included
    if charitable_cash + charitable_noncash > 0:
        c = _get_constants(tax_year)
        fs = est.filing_status
        mortgage_interest = sum(
            f.mortgage_interest_received or 0.0 for f in result.form_1098
        )
        real_estate_taxes = sum(f.real_estate_taxes or 0.0 for f in result.form_1098)
        state_taxes = sum(w2.box17_state_tax or 0.0 for w2 in result.w2)
        salt = min(state_taxes + real_estate_taxes, c["salt_cap"][fs])
        itemized = mortgage_interest + salt + charitable_cash + charitable_noncash
        std_ded = c["standard_deductions"][fs]
        if itemized > est.deduction_used or itemized > std_ded:
            # Recompute with new itemized total — call calculate_tax again
            # Simpler: just patch itemized deduction and recalculate downstream
            est2 = calculate_tax(
                result,
                filing_status=filing_status,
                num_children=num_children,
                estimated_payments=estimated_payments,
                foreign_tax_credit=foreign_tax_credit,
                tax_year=tax_year,
            )
            # Monkey-patch the itemized total to include charitable
            old_deduction = est2.deduction_used
            if itemized > std_ded:
                delta = itemized - est2.itemized_deduction
                est2.itemized_deduction = itemized
                if est2.deduction_type == "itemized":
                    est2.deduction_used = itemized
                    est2.taxable_income = max(0.0, est2.agi - itemized - est2.qbi_deduction)
                elif itemized > std_ded:
                    est2.deduction_type = "itemized"
                    est2.deduction_used = itemized
                    est2.taxable_income = max(0.0, est2.agi - itemized - est2.qbi_deduction)
                    est2.notes.append(
                        f"Itemized deductions (${itemized:,.0f}) exceed standard deduction "
                        f"(${std_ded:,.0f}) after adding charitable contributions. Using itemized."
                    )
            return est2

    return est


def _f(v) -> Optional[float]:
    """Safely coerce a value to float, returning None for None/empty."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
