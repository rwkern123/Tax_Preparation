from __future__ import annotations

import re
from typing import Optional

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text
from src.models import Brokerage1099Data


def _money(label_pattern: str, text: str) -> Optional[float]:
    return extract_amount_after_label(label_pattern, text)


def parse_brokerage_1099_text(text: str) -> Brokerage1099Data:
    data = Brokerage1099Data()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    broker_match = re.search(r"(?:Broker|Payer|Financial Institution)[:\s]+(.+)", text, re.IGNORECASE)
    if broker_match:
        data.broker_name = broker_match.group(1).strip()[:120]

    data.div_ordinary = _money(r"ordinary\s+dividends", text)
    data.div_qualified = _money(r"qualified\s+dividends", text)
    data.div_cap_gain_distributions = _money(r"capital\s+gain\s+distributions", text)
    data.div_foreign_tax_paid = _money(r"foreign\s+tax\s+paid", text)

    data.int_interest_income = _money(r"interest\s+income", text)
    data.int_us_treasury = _money(r"us\s+treasury\s+interest|treasury\s+obligations", text)

    summary_labels = {
        "proceeds": r"total\s+proceeds",
        "cost_basis": r"cost\s+basis",
        "wash_sales": r"wash\s+sale",
        "short_term_gain_loss": r"short[-\s]term\s+(?:gain|loss)",
        "long_term_gain_loss": r"long[-\s]term\s+(?:gain|loss)",
    }
    for key, pattern in summary_labels.items():
        data.b_summary[key] = _money(pattern, text)

    populated = sum(
        1
        for v in [
            data.div_ordinary,
            data.div_qualified,
            data.div_cap_gain_distributions,
            data.div_foreign_tax_paid,
            data.int_interest_income,
            data.int_us_treasury,
            *data.b_summary.values(),
        ]
        if v is not None
    )
    data.confidence = round(min(1.0, populated / 9 + 0.15), 2)
    return data
