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

    lines += ["## C) 1099-DIV/INT entry"]
    if data.brokerage_1099:
        idx = 1
        for b in data.brokerage_1099:
            lines.append(
                f"{idx}. Enter 1099-DIV/INT from {b.broker_name or 'Unknown Broker'}: Ordinary={_fmt_money(b.div_ordinary)}, Qualified={_fmt_money(b.div_qualified)}, Interest={_fmt_money(b.int_interest_income)}."
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
    lines.append("")

    lines += ["## E) Deductions/credits prompts", "1. Confirm standard vs. itemized deduction."]
    if data.form_1098:
        for idx, form in enumerate(data.form_1098, 2):
            lines.append(
                f"{idx}. Enter Form 1098 from {form.lender_name or 'Unknown Lender'} for payer {form.payer_name or 'unknown'}: Mortgage Interest={_fmt_money(form.mortgage_interest_received)}, Points={_fmt_money(form.points_paid)}, Real Estate Taxes={_fmt_money(form.real_estate_taxes)}."
            )
    else:
        lines.append("2. Ask whether mortgage interest (Form 1098) applies and request statements if itemizing.")
    lines.append("3. Ask about charitable donations and other itemized deductions.")
    lines.append("")

    lines += [
        "## F) Review & diagnostics",
        "1. Reconcile total W-2 wages and withholding against source forms.",
        "2. Assess withholding reasonableness and compare with prior-year fields if available.",
        "",
        "## G) E-file/admin (placeholder)",
        "1. Run final diagnostics and complete e-file authorization workflow.",
    ]

    return "\n".join(lines)
