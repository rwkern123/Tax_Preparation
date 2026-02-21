from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import json


@dataclass
class ComparisonMetric:
    name: str
    current: Optional[float]
    prior: Optional[float]

    @property
    def delta(self) -> Optional[float]:
        if self.current is None or self.prior is None:
            return None
        return self.current - self.prior

    @property
    def pct_change(self) -> Optional[float]:
        if self.delta is None or self.prior in (None, 0):
            return None
        return (self.delta / self.prior) * 100.0


def _sum_numbers(items: list[dict[str, Any]], key: str) -> Optional[float]:
    values = [i.get(key) for i in items if isinstance(i.get(key), (int, float))]
    if not values:
        return None
    return float(sum(values))


def _sum_nested_numbers(items: list[dict[str, Any]], nested_key: str, key: str) -> Optional[float]:
    vals: list[float] = []
    for item in items:
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            val = nested.get(key)
            if isinstance(val, (int, float)):
                vals.append(float(val))
    if not vals:
        return None
    return float(sum(vals))


def build_metrics(current_extract: dict[str, Any], prior_extract: dict[str, Any]) -> list[ComparisonMetric]:
    cur_w2 = current_extract.get("w2", []) if isinstance(current_extract.get("w2"), list) else []
    prv_w2 = prior_extract.get("w2", []) if isinstance(prior_extract.get("w2"), list) else []

    cur_b = current_extract.get("brokerage_1099", []) if isinstance(current_extract.get("brokerage_1099"), list) else []
    prv_b = prior_extract.get("brokerage_1099", []) if isinstance(prior_extract.get("brokerage_1099"), list) else []

    cur_1098 = current_extract.get("form_1098", []) if isinstance(current_extract.get("form_1098"), list) else []
    prv_1098 = prior_extract.get("form_1098", []) if isinstance(prior_extract.get("form_1098"), list) else []

    return [
        ComparisonMetric("W-2 total wages (Box 1)", _sum_numbers(cur_w2, "box1_wages"), _sum_numbers(prv_w2, "box1_wages")),
        ComparisonMetric("W-2 federal withholding (Box 2)", _sum_numbers(cur_w2, "box2_fed_withholding"), _sum_numbers(prv_w2, "box2_fed_withholding")),
        ComparisonMetric("1099 ordinary dividends", _sum_numbers(cur_b, "div_ordinary"), _sum_numbers(prv_b, "div_ordinary")),
        ComparisonMetric("1099 interest income", _sum_numbers(cur_b, "int_interest_income"), _sum_numbers(prv_b, "int_interest_income")),
        ComparisonMetric("1099-B wash sales", _sum_nested_numbers(cur_b, "b_summary", "wash_sales"), _sum_nested_numbers(prv_b, "b_summary", "wash_sales")),
        ComparisonMetric("1098 mortgage interest", _sum_numbers(cur_1098, "mortgage_interest_received"), _sum_numbers(prv_1098, "mortgage_interest_received")),
        ComparisonMetric("1098 real estate taxes", _sum_numbers(cur_1098, "real_estate_taxes"), _sum_numbers(prv_1098, "real_estate_taxes")),
    ]


def generate_comparison_markdown(client: str, current_year: int, prior_year: int, metrics: list[ComparisonMetric]) -> str:
    lines = [
        f"# Prior Year Comparison - {client}",
        "",
        f"Current year: {current_year}",
        f"Prior year: {prior_year}",
        "",
        "| Metric | Current | Prior | Delta | % Change |",
        "|---|---:|---:|---:|---:|",
    ]

    def fmt(v: Optional[float]) -> str:
        return "N/A" if v is None else f"{v:,.2f}"

    def fmt_pct(v: Optional[float]) -> str:
        return "N/A" if v is None else f"{v:.1f}%"

    for m in metrics:
        lines.append(f"| {m.name} | {fmt(m.current)} | {fmt(m.prior)} | {fmt(m.delta)} | {fmt_pct(m.pct_change)} |")

    lines += ["", "## Review flags"]
    flagged = 0
    for m in metrics:
        if m.pct_change is not None and abs(m.pct_change) >= 20:
            lines.append(f"- Large year-over-year change in **{m.name}** ({m.pct_change:+.1f}%). Verify source docs and return entries.")
            flagged += 1
    if flagged == 0:
        lines.append("- No large (>20%) year-over-year changes detected among compared metrics.")

    return "\n".join(lines)


def load_extract(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
