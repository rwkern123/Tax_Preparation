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

    for sc in data.schedule_c:
        biz = sc.line_c_business_name or sc.line_a_principal_business or "your business"
        if sc.line_i_made_payments_requiring_1099 and sc.line_j_filed_required_1099 is False:
            q.append(
                f"- For {biz}: you indicated you made payments requiring 1099s but did NOT file them. "
                f"Please collect outstanding W-9s and prepare any unfiled 1099-NECs/1099-MISCs before we file."
            )
        if sc.line_30_home_office and sc.line_30_home_office > 0 and not sc.line_30_simplified_method_business_sqft:
            q.append(
                f"- For {biz}: home office deduction reported (line 30 = {_fmt_money(sc.line_30_home_office)}). "
                f"Are you using the simplified method or actual expenses (Form 8829)? "
                f"If actual, please confirm direct/indirect expense allocations and depreciation basis."
            )
        if sc.line_9_car_truck and sc.line_9_car_truck > 0 and sc.line_44a_business_miles is None:
            q.append(
                f"- For {biz}: car/truck expenses reported (line 9 = {_fmt_money(sc.line_9_car_truck)}) "
                f"but Part IV vehicle mileage is missing. Please provide business/commuting/other miles for the year."
            )
        if sc.line_47a_evidence_to_support is False:
            q.append(
                f"- For {biz}: line 47a indicates no documentation supporting the vehicle deduction. "
                f"This is high audit risk — can you produce a mileage log or other contemporaneous evidence?"
            )
        if sc.line_31_net_profit_loss is not None and sc.line_31_net_profit_loss < 0:
            q.append(
                f"- For {biz}: a loss of {_fmt_money(sc.line_31_net_profit_loss)} was reported. "
                f"Confirm at-risk basis (line 32a vs 32b) and whether you materially participated. "
                f"Repeated losses may attract IRS hobby-loss scrutiny under §183."
            )
        if sc.line_24b_meals and sc.line_22_supplies and sc.line_24b_meals > sc.line_22_supplies * 2:
            q.append(
                f"- For {biz}: deductible meals (line 24b) appear large relative to supplies. "
                f"Confirm meals are with clients/employees, not personal, and 50% limit was applied."
            )
        if sc.line_g_material_participation is False:
            q.append(
                f"- For {biz}: line G indicates you did NOT materially participate. "
                f"Losses may be limited as passive activity (Form 8582). Was this intended?"
            )
        if sc.line_h_started_or_acquired:
            q.append(
                f"- For {biz}: line H indicates the business started or was acquired this year. "
                f"Did you incur start-up costs >$5,000 (§195) or organizational costs (§248) that should be amortized?"
            )

    if not data.form_1099_nec and not data.w2 and not data.schedule_c:
        q.append("- No W-2 or 1099-NEC found. Did you have any wage or self-employment income this year?")

    if len(q) == 2:
        q.append("- No follow-up items detected from available source documents.")

    return "\n".join(q)
