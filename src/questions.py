from __future__ import annotations

from src.models import ExtractionResult


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

    for w in data.w2:
        if len(w.states) > 1:
            q.append("- Multiple states appear on W-2. Please confirm resident/nonresident status and move dates.")
        if "D" in w.box12:
            q.append("- Box 12 code D detected. Confirm retirement plan contribution details.")

    for form in data.form_1098:
        if not form.payer_name:
            q.append("- Form 1098 detected without a clear payer/borrower name. Please confirm whether this is taxpayer, spouse, or joint.")
        elif "joint" not in form.payer_name.lower() and len(data.w2) > 1:
            q.append("- Form 1098 appears individual while return may be MFJ. Confirm whether mortgage interest is individual or joint and how title/loan are held.")

    if len(q) == 2:
        q.append("- No follow-up items detected from available source documents.")

    return "\n".join(q)
