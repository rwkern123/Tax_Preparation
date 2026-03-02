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
    box16_state_wages: Optional[float] = None
    box17_state_tax: Optional[float] = None
    states: List[str] = field(default_factory=list)
    localities: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class Brokerage1099Data:
    broker_name: Optional[str] = None
    year: Optional[int] = None
    div_ordinary: Optional[float] = None
    div_qualified: Optional[float] = None
    div_cap_gain_distributions: Optional[float] = None
    div_foreign_tax_paid: Optional[float] = None
    int_interest_income: Optional[float] = None
    int_us_treasury: Optional[float] = None
    b_summary: Dict[str, Optional[float]] = field(default_factory=dict)
    confidence: float = 0.0


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
class ExtractionResult:
    w2: List[W2Data] = field(default_factory=list)
    brokerage_1099: List[Brokerage1099Data] = field(default_factory=list)
    brokerage_1099_trades: List[Brokerage1099Trade] = field(default_factory=list)
    form_1098: List[Form1098Data] = field(default_factory=list)
    unknown: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "w2": [asdict(item) for item in self.w2],
            "brokerage_1099": [asdict(item) for item in self.brokerage_1099],
            "brokerage_1099_trades": [asdict(item) for item in self.brokerage_1099_trades],
            "form_1098": [asdict(item) for item in self.form_1098],
            "unknown": self.unknown,
        }
