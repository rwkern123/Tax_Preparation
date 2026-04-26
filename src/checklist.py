from __future__ import annotations

from src.models import ExtractionResult


def _fmt_money(v: float | None) -> str:
    return "N/A" if v is None else f"${v:,.2f}"


def generate_checklist(client: str, data: ExtractionResult) -> str:
    lines: list[str] = [f"# Return Prep Checklist - {client}", ""]

    lines += ["## A) Intake & admin", "1. Confirm engagement/authorization and filing status.", "2. Verify tax year documents are complete.", ""]

    lines += ["## B) W-2 entry + reconciliation notes"]
    if data.w2:
        for i, w2 in enumerate(data.w2, 1):
            lines.append(
                f"{i}. Enter W-2 from {w2.employer_name or 'Unknown Employer'} "
                f"(EIN {w2.employer_ein or 'unknown'}): Box 1={_fmt_money(w2.box1_wages)}, Box 2={_fmt_money(w2.box2_fed_withholding)}, Box 16={_fmt_money(w2.box16_state_wages)}, Box 17={_fmt_money(w2.box17_state_tax)}."
            )
    else:
        lines.append("1. No W-2 detected; request wage statements if employment income exists.")
    lines.append("")

    lines += ["## C) 1099 Composite / DIV / INT entry"]
    if data.brokerage_1099:
        idx = 1
        for b in data.brokerage_1099:
            sec199a_part = (
                f", Sec199A={_fmt_money(b.div_section_199a)}" if b.div_section_199a is not None else ""
            )
            lines.append(
                f"{idx}. Enter 1099-DIV/INT from {b.broker_name or 'Unknown Broker'}: Ordinary={_fmt_money(b.div_ordinary)}, Qualified={_fmt_money(b.div_qualified)}, Interest={_fmt_money(b.int_interest_income)}{sec199a_part}."
            )
            idx += 1
    else:
        lines.append("1. No brokerage 1099 detected; ask whether investment income documents are missing.")
    lines.append("")

    lines += ["## D) 1099-B summary entry + wash sale notes"]
    if data.brokerage_1099:
        for i, b in enumerate(data.brokerage_1099, 1):
            ws = b.b_summary.get("wash_sales")
            lines.append(
                f"{i}. Enter 1099-B summary from {b.broker_name or 'Unknown Broker'}: Proceeds={_fmt_money(b.b_summary.get('proceeds'))}, Cost Basis={_fmt_money(b.b_summary.get('cost_basis'))}, Wash Sales={_fmt_money(ws)}."
            )
            if ws and ws > 0:
                lines.append("   - If wash sales > 0, verify basis adjustments and carryover treatment.")
    else:
        lines.append("1. No 1099-B summary found.")

    if data.brokerage_1099_trades:
        lines.append(
            f"- Trade-level 1099-B extraction produced {len(data.brokerage_1099_trades)} rows; review 1099b_trades_tax.csv and 1099b_reconciliation.json, then tie totals to broker subtotals."
        )
    for b in data.brokerage_1099:
        if b.section_1256_net_gain_loss is not None:
            lines.append(
                f"- Section 1256 contracts present — enter aggregate gain/loss on Form 6781: {_fmt_money(b.section_1256_net_gain_loss)} ({b.broker_name or 'Unknown Broker'})."
            )
    lines.append("")

    lines += ["## E) 1099-NEC / Self-Employment Income"]
    if data.form_1099_nec:
        for i, nec in enumerate(data.form_1099_nec, 1):
            withheld_part = f", Box 4 Fed Withheld={_fmt_money(nec.box4_fed_withholding)}" if nec.box4_fed_withholding else ""
            lines.append(
                f"{i}. Enter 1099-NEC from {nec.payer_name or 'Unknown Payer'}: "
                f"Box 1 Nonemployee Comp={_fmt_money(nec.box1_nonemployee_compensation)}{withheld_part}."
            )
            if nec.box1_nonemployee_compensation and nec.box1_nonemployee_compensation > 0:
                lines.append(
                    f"   - Self-employment income — determine if Schedule C applies. "
                    f"Evaluate SE tax and estimated payment obligations."
                )
            if nec.is_corrected:
                lines.append(f"   - NOTE: This is a CORRECTED 1099-NEC. Verify against original.")
    else:
        lines.append("1. No 1099-NEC detected. Ask whether client received any freelance, contract, or gig income.")
    lines.append("")

    lines += ["## F) 1099-R Retirement / Pension / IRA Distributions"]
    if data.form_1099_r:
        for i, r in enumerate(data.form_1099_r, 1):
            code_part = f", Code={r.box7_distribution_code}" if r.box7_distribution_code else ""
            withheld_part = f", Fed Withheld={_fmt_money(r.box4_fed_withholding)}" if r.box4_fed_withholding else ""
            lines.append(
                f"{i}. Enter 1099-R from {r.payer_name or 'Unknown Payer'}: "
                f"Gross={_fmt_money(r.box1_gross_distribution)}, Taxable={_fmt_money(r.box2a_taxable_amount)}"
                f"{code_part}{withheld_part}."
            )
            if r.box7_distribution_code in ("1", "J"):
                lines.append(
                    f"   - Distribution code {r.box7_distribution_code} indicates early distribution — evaluate 10% penalty (Form 5329) and any exceptions."
                )
            if r.box7_distribution_code == "G":
                lines.append("   - Code G = direct rollover. Confirm rollover destination and verify no taxable amount.")
            if r.box7_ira_sep_simple:
                lines.append("   - IRA/SEP/SIMPLE box checked. Confirm basis (Form 8606) if after-tax contributions exist.")
            if r.box2b_taxable_not_determined:
                lines.append("   - 'Taxable amount not determined' checked — manually determine taxable portion.")
            if r.is_corrected:
                lines.append("   - NOTE: This is a CORRECTED 1099-R. Verify against original.")
    else:
        lines.append("1. No 1099-R detected. Ask whether client received any retirement, pension, IRA, or annuity distributions.")
    lines.append("")

    lines += ["## G) Social Security Benefits (SSA-1099)"]
    if data.ssa_1099:
        for i, ssa in enumerate(data.ssa_1099, 1):
            withheld_part = f", Box 6 Fed Withheld={_fmt_money(ssa.box6_voluntary_tax_withheld)}" if ssa.box6_voluntary_tax_withheld else ""
            lines.append(
                f"{i}. Enter SSA-1099 for {ssa.beneficiary_name or 'Unknown Beneficiary'}: "
                f"Box 5 Net Benefits={_fmt_money(ssa.box5_net_benefits)}"
                f"{withheld_part} → Form 1040 Line 6a."
            )
            if ssa.box5_is_negative:
                lines.append(
                    "   - Box 5 is NEGATIVE (repayments exceeded gross benefits). "
                    "None of this year's benefits are taxable; see Pub. 915 'Repayments More Than Gross Benefits'."
                )
            if ssa.lump_sum_prior_years and ssa.lump_sum_prior_years > 0:
                lines.append(
                    f"   - LUMP-SUM: Box 3 includes {_fmt_money(ssa.lump_sum_prior_years)} paid in {ssa.year} for earlier years. "
                    f"Consider lump-sum election method (check box on Form 1040 Line 6c and complete Worksheet 2/Pub. 915)."
                )
            if ssa.box4_benefits_repaid and ssa.box4_benefits_repaid > 0:
                lines.append(
                    f"   - Benefits repaid to SSA (Box 4)={_fmt_money(ssa.box4_benefits_repaid)}. "
                    f"If repayments exceed $3,000, evaluate Sec. 1341 claim-of-right deduction."
                )
            if ssa.medicare_premiums:
                lines.append(
                    f"   - Medicare premiums deducted from benefits={_fmt_money(ssa.medicare_premiums)}. "
                    f"Include in Schedule A medical expenses if itemizing (not subtracted from Box 5)."
                )
            if ssa.attorney_fees_withheld:
                lines.append(
                    f"   - Attorney fees withheld from benefits={_fmt_money(ssa.attorney_fees_withheld)}. "
                    f"Included in Box 3; do not subtract from Box 5."
                )
            if ssa.is_corrected:
                lines.append("   - NOTE: This is a CORRECTED SSA-1099. Verify against original.")
    else:
        lines.append("1. No SSA-1099 detected. Ask whether client (or spouse) received Social Security benefits.")
    lines.append("")

    lines += ["## H) Deductions/credits prompts", "1. Confirm standard vs. itemized deduction."]
    if data.form_1098:
        for idx, form in enumerate(data.form_1098, 2):
            lines.append(
                f"{idx}. Enter Form 1098 from {form.lender_name or 'Unknown Lender'} for payer {form.payer_name or 'unknown'}: Mortgage Interest={_fmt_money(form.mortgage_interest_received)}, Points={_fmt_money(form.points_paid)}, Real Estate Taxes={_fmt_money(form.real_estate_taxes)}."
            )
    else:
        lines.append("2. Ask whether mortgage interest (Form 1098) applies and request statements if itemizing.")
    if any((b.div_section_199a or 0) > 0 for b in data.brokerage_1099):
        lines.append("- Section 199A dividends present — evaluate Form 8995 / QBI deduction.")
    if any((b.div_foreign_tax_paid or 0) > 0 for b in data.brokerage_1099):
        lines.append("- Foreign tax paid — evaluate Form 1116 foreign tax credit.")
    lines.append("3. Ask about charitable donations and other itemized deductions.")
    lines.append("")

    lines += [
        "## I) Review & diagnostics",
        "1. Reconcile total W-2 wages and withholding against source forms.",
        "2. Assess withholding reasonableness and compare with prior-year fields if available.",
        "",
        "## J) E-file/admin (placeholder)",
        "1. Run final diagnostics and complete e-file authorization workflow.",
    ]

    return "\n".join(lines)
