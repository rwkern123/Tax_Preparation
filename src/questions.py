from __future__ import annotations

from src.models import ExtractionResult


def _fmt_money(v: float | None) -> str:
    return "N/A" if v is None else f"${v:,.2f}"


def generate_questions(client: str, data: ExtractionResult) -> str:
    q: list[str] = [f"# Questions For Client - {client}", ""]

    has_w2 = len(data.w2) > 0
    has_brokerage = len(data.brokerage_1099) > 0

    if has_w2 and not has_brokerage:
        q.append("- We found W-2 forms but no brokerage 1099s. Do you have any 1099-DIV/INT/B documents?")
    if has_brokerage and not has_w2:
        q.append("- We found brokerage tax statements but no W-2. Did you have wage income requiring a W-2?")

    for b in data.brokerage_1099:
        if (b.div_foreign_tax_paid or 0) > 0:
            q.append("- Foreign tax paid was reported. Should we evaluate foreign tax credit eligibility?")
        if b.section_1256_net_gain_loss is not None:
            q.append("- Section 1256 (mark-to-market) contracts detected. Confirm all Form 6781 entries are complete.")
        if (b.div_section_199a or 0) > 0:
            q.append("- Section 199A dividends reported. Do you want to evaluate the QBI deduction on Form 8995?")


    if data.brokerage_1099 and not data.brokerage_1099_trades:
        q.append("- Brokerage statements were detected but no trade-level 1099-B rows were parsed. Please provide clearer copies or CSV exports from your broker.")

    for w in data.w2:
        if (
            w.employer_state
            and w.employee_state
            and w.employer_state != w.employee_state
        ):
            q.append("- Multiple states appear on W-2. Please confirm resident/nonresident status and move dates.")
        if "D" in w.box12:
            q.append("- Box 12 code D detected. Confirm retirement plan contribution details.")

    for form in data.form_1098:
        if not form.payer_name:
            q.append("- Form 1098 detected without a clear payer/borrower name. Please confirm whether this is taxpayer, spouse, or joint.")
        elif "joint" not in form.payer_name.lower() and len(data.w2) > 1:
            q.append("- Form 1098 appears individual while return may be MFJ. Confirm whether mortgage interest is individual or joint and how title/loan are held.")

    for nec in data.form_1099_nec:
        if nec.box1_nonemployee_compensation and nec.box1_nonemployee_compensation > 0:
            q.append(
                f"- 1099-NEC received from {nec.payer_name or 'unknown payer'} "
                f"({_fmt_money(nec.box1_nonemployee_compensation)}). "
                f"Did you have any business expenses related to this work to report on Schedule C?"
            )
        if not nec.box4_fed_withholding:
            q.append(
                "- No federal withholding on 1099-NEC. Were estimated tax payments made during the year? "
                "If not, an underpayment penalty may apply."
            )

    for r in data.form_1099_r:
        if r.box7_distribution_code in ("1", "J"):
            q.append(
                f"- Early retirement distribution (code {r.box7_distribution_code}) from "
                f"{r.payer_name or 'unknown payer'} ({_fmt_money(r.box1_gross_distribution)}). "
                f"Do any exceptions to the 10% early withdrawal penalty apply (e.g., disability, medical, separation from service at age 55+)?"
            )
        if r.box7_ira_sep_simple and r.box2b_taxable_not_determined:
            q.append(
                "- IRA/SEP/SIMPLE distribution with taxable amount not determined. "
                "Have you made any nondeductible (after-tax) IRA contributions? If so, Form 8606 is required to calculate the taxable portion."
            )
        if r.box7_distribution_code == "G":
            q.append(
                f"- Rollover distribution from {r.payer_name or 'unknown payer'}. "
                f"Please confirm the rollover was deposited into the destination account within 60 days."
            )
        if not r.box4_fed_withholding:
            q.append(
                f"- No federal tax was withheld on the distribution from {r.payer_name or 'unknown payer'}. "
                f"Were estimated payments made to cover the tax due on this distribution?"
            )

    if not data.form_1099_nec and not data.w2:
        q.append("- No W-2 or 1099-NEC found. Did you have any wage or self-employment income this year?")

    if len(q) == 2:
        q.append("- No follow-up items detected from available source documents.")

    return "\n".join(q)
