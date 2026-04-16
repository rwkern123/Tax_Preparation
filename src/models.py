from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DocumentRecord:
    client: str
    file_path: str
    file_name: str
    sha256: str
    doc_type: str
    confidence: float
    detected_year: Optional[int] = None
    issuer: Optional[str] = None
    key_fields: Dict[str, Any] = field(default_factory=dict)
    extraction_notes: List[str] = field(default_factory=list)


@dataclass
class W2Data:
    employer_name: Optional[str] = None
    employer_ein: Optional[str] = None
    employee_name: Optional[str] = None
    year: Optional[int] = None
    box1_wages: Optional[float] = None
    box2_fed_withholding: Optional[float] = None
    box3_ss_wages: Optional[float] = None
    box4_ss_tax: Optional[float] = None
    box5_medicare_wages: Optional[float] = None
    box6_medicare_tax: Optional[float] = None
    box12: Dict[str, float] = field(default_factory=dict)
    box13_retirement_plan: bool = False
    box16_state_wages: Optional[float] = None
    box17_state_tax: Optional[float] = None
    employer_address: Optional[str] = None
    employer_city: Optional[str] = None
    employer_state: Optional[str] = None
    employer_zip: Optional[str] = None
    employee_address: Optional[str] = None
    employee_city: Optional[str] = None
    employee_state: Optional[str] = None
    employee_zip: Optional[str] = None
    confidence: float = 0.0
    extraction_source: str = "local"  # "local" | "azure"


@dataclass
class Brokerage1099Data:
    broker_name: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    div_ordinary: Optional[float] = None
    div_qualified: Optional[float] = None
    div_cap_gain_distributions: Optional[float] = None
    div_foreign_tax_paid: Optional[float] = None
    div_section_199a: Optional[float] = None
    int_interest_income: Optional[float] = None
    int_us_treasury: Optional[float] = None
    section_1256_net_gain_loss: Optional[float] = None
    b_short_term_covered: Optional[float] = None
    b_short_term_noncovered: Optional[float] = None
    b_long_term_covered: Optional[float] = None
    b_long_term_noncovered: Optional[float] = None
    b_summary: Dict[str, Optional[float]] = field(default_factory=dict)
    confidence: float = 0.0
    extraction_source: str = "local"  # "local" | "azure"

    def __post_init__(self) -> None:
        # Populate b_summary covered/noncovered breakdown from the typed fields so
        # downstream consumers that read b_summary continue to work unchanged.
        covered_map = {
            "short_term_covered": self.b_short_term_covered,
            "short_term_noncovered": self.b_short_term_noncovered,
            "long_term_covered": self.b_long_term_covered,
            "long_term_noncovered": self.b_long_term_noncovered,
        }
        for key, value in covered_map.items():
            if value is not None and key not in self.b_summary:
                self.b_summary[key] = value


@dataclass
class Brokerage1099Trade:
    broker_name: Optional[str] = None
    source_file: Optional[str] = None
    source_sha256: Optional[str] = None
    source_page: Optional[int] = None
    description: str = ""
    security_identifier: Optional[str] = None
    date_acquired: Optional[str] = None
    date_sold_or_disposed: Optional[str] = None
    proceeds_gross: Optional[float] = None
    cost_basis: Optional[float] = None
    wash_sale_code: Optional[str] = None
    wash_sale_amount: Optional[float] = None
    federal_income_tax_withheld: Optional[float] = None
    holding_period: str = "unknown"
    basis_reported_to_irs: str = "unknown"
    adjustment_code: Optional[str] = None
    adjustment_amount: Optional[float] = None
    realized_gain_loss: Optional[float] = None
    form_8949_box: str = ""
    raw_trade_line: Optional[str] = None


@dataclass
class Form1098Data:
    lender_name: Optional[str] = None
    payer_name: Optional[str] = None
    borrower_names: List[str] = field(default_factory=list)
    year: Optional[int] = None
    mortgage_interest_received: Optional[float] = None
    points_paid: Optional[float] = None
    mortgage_insurance_premiums: Optional[float] = None
    real_estate_taxes: Optional[float] = None
    mortgage_principal_outstanding: Optional[float] = None
    confidence: float = 0.0


@dataclass
class Form1099NECData:
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    recipient_street: Optional[str] = None
    recipient_city_state_zip: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_nonemployee_compensation: Optional[float] = None
    box2_direct_sales: bool = False
    box3_excess_golden_parachute: Optional[float] = None
    box4_fed_withholding: Optional[float] = None
    box5_state_tax_withheld: Optional[float] = None
    box6_state_payer_no: Optional[str] = None
    box7_state_income: Optional[float] = None
    is_corrected: bool = False
    confidence: float = 0.0


@dataclass
class PriorYearReturnData:
    """Key fields extracted from a prior-year Form 1040 tax return PDF."""

    # Header / identity
    year: Optional[int] = None
    taxpayer_name: Optional[str] = None
    taxpayer_ssn: Optional[str] = None
    spouse_name: Optional[str] = None
    spouse_ssn: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    filing_status: Optional[str] = None

    # Income (Form 1040 lines)
    line_1a_w2_wages: Optional[float] = None          # W-2 box 1 total
    line_1z_total_wages: Optional[float] = None       # Sum of lines 1a–1h
    line_2b_taxable_interest: Optional[float] = None
    line_3a_qualified_dividends: Optional[float] = None
    line_3b_ordinary_dividends: Optional[float] = None
    line_4b_ira_taxable: Optional[float] = None
    line_5b_pension_taxable: Optional[float] = None
    line_6b_ss_taxable: Optional[float] = None
    line_7_capital_gain_loss: Optional[float] = None
    line_8_other_income: Optional[float] = None       # Schedule 1 line 10
    line_9_total_income: Optional[float] = None
    line_10_adjustments: Optional[float] = None
    line_11_agi: Optional[float] = None
    line_12_deductions: Optional[float] = None        # Standard or itemized
    line_13_qbi_deduction: Optional[float] = None
    line_15_taxable_income: Optional[float] = None

    # Tax & credits
    line_16_tax: Optional[float] = None
    line_24_total_tax: Optional[float] = None

    # Payments
    line_25a_w2_withholding: Optional[float] = None
    line_25b_1099_withholding: Optional[float] = None
    line_25d_total_withholding: Optional[float] = None
    line_26_estimated_payments: Optional[float] = None
    line_33_total_payments: Optional[float] = None

    # Refund / balance due
    line_34_overpayment: Optional[float] = None
    line_35a_refund: Optional[float] = None
    line_37_amount_owed: Optional[float] = None
    line_38_estimated_tax_penalty: Optional[float] = None

    confidence: float = 0.0
    extraction_source: str = "local"  # "local" | "azure"


@dataclass
class ExtractionResult:
    w2: List[W2Data] = field(default_factory=list)
    brokerage_1099: List[Brokerage1099Data] = field(default_factory=list)
    brokerage_1099_trades: List[Brokerage1099Trade] = field(default_factory=list)
    form_1098: List[Form1098Data] = field(default_factory=list)
    form_1099_nec: List[Form1099NECData] = field(default_factory=list)
    unknown: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "w2": [asdict(item) for item in self.w2],
            "brokerage_1099": [asdict(item) for item in self.brokerage_1099],
            "brokerage_1099_trades": [asdict(item) for item in self.brokerage_1099_trades],
            "form_1098": [asdict(item) for item in self.form_1098],
            "form_1099_nec": [asdict(item) for item in self.form_1099_nec],
            "unknown": self.unknown,
        }
