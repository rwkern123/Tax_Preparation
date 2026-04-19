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
    extraction_source: str = "local"  # "local" | "azure"


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
class Form1099RData:
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_gross_distribution: Optional[float] = None
    box2a_taxable_amount: Optional[float] = None
    box2b_taxable_not_determined: bool = False
    box2b_total_distribution: bool = False
    box3_capital_gain: Optional[float] = None
    box4_fed_withholding: Optional[float] = None
    box5_employee_contributions: Optional[float] = None
    box7_distribution_code: Optional[str] = None
    box7_ira_sep_simple: bool = False
    box14_state_tax_withheld: Optional[float] = None
    box15_state_payer_no: Optional[str] = None
    box16_state_distribution: Optional[float] = None
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

    # Additional 1040 header fields
    taxpayer_occupation: Optional[str] = None
    spouse_occupation: Optional[str] = None
    dependents: List[Dict] = field(default_factory=list)  # [{name, ssn, relationship, ctc_eligible, odc_eligible}]
    refund_applied_forward: Optional[float] = None   # Line 36 — refund applied to next-year estimated tax
    extension_filed: bool = False                    # Form 4868 indicator

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

    # Schedule 1 adjustments
    sched1_educator_expenses: Optional[float] = None
    sched1_hsa_deduction: Optional[float] = None
    sched1_ira_deduction: Optional[float] = None
    sched1_student_loan_interest: Optional[float] = None
    sched1_nol_deduction: Optional[float] = None

    # Schedule A — Itemized Deductions
    sched_a_present: bool = False
    sched_a_medical_dental: Optional[float] = None
    sched_a_salt_total: Optional[float] = None
    sched_a_mortgage_interest: Optional[float] = None
    sched_a_charitable_cash: Optional[float] = None
    sched_a_charitable_noncash: Optional[float] = None
    sched_a_charitable_carryforward: Optional[float] = None
    sched_a_investment_interest: Optional[float] = None
    sched_a_total_itemized: Optional[float] = None

    # Schedule B — Interest & Dividends
    sched_b_present: bool = False
    sched_b_foreign_account: Optional[bool] = None  # Part III Q7a

    # Schedule C — Business Activity
    sched_c_present: bool = False
    sched_c_businesses: List[Dict] = field(default_factory=list)  # [{name, ein, accounting_method, net_profit_loss}]

    # Schedule D — Capital Gains & Losses
    sched_d_present: bool = False
    sched_d_net_stcg: Optional[float] = None
    sched_d_net_ltcg: Optional[float] = None
    sched_d_capital_loss_carryforward: Optional[float] = None

    # Schedule E — Rental & Pass-Through Activity
    sched_e_present: bool = False
    sched_e_rental_properties: List[str] = field(default_factory=list)
    sched_e_total_rental_income: Optional[float] = None
    sched_e_total_rental_loss: Optional[float] = None
    sched_e_k1_partnerships: bool = False
    sched_e_k1_s_corps: bool = False
    sched_e_k1_trusts: bool = False

    # Form 4562 — Depreciation & Section 179
    form_4562_present: bool = False
    form_4562_section_179_deduction: Optional[float] = None
    form_4562_section_179_carryforward: Optional[float] = None
    form_4562_bonus_depreciation: Optional[float] = None

    # Form 8582 — Passive Activity Loss Limitations
    form_8582_present: bool = False
    form_8582_pal_carryforward: Optional[float] = None
    form_8582_rental_loss_carryforward: Optional[float] = None

    # Form 8606 — IRA Basis Tracking
    form_8606_present: bool = False
    form_8606_ira_basis: Optional[float] = None
    form_8606_nondeductible_contributions: Optional[float] = None

    # Form 8829 — Home Office
    form_8829_present: bool = False
    form_8829_carryforward: Optional[float] = None

    # Form 8995 / 8995-A — Qualified Business Income
    form_8995_present: bool = False
    form_8995_qbi_loss_carryforward: Optional[float] = None

    # Form 1116 — Foreign Tax Credit
    form_1116_present: bool = False
    form_1116_foreign_tax_credit: Optional[float] = None
    form_1116_carryforward: Optional[float] = None

    # Form 3800 — General Business Credit
    form_3800_present: bool = False
    form_3800_credit_carryforward: Optional[float] = None

    # Form 6251 — AMT
    form_6251_present: bool = False
    form_6251_amt: Optional[float] = None
    form_6251_amt_credit_carryforward: Optional[float] = None

    # Form 6252 — Installment Sales
    form_6252_present: bool = False
    form_6252_gross_profit_pct: Optional[float] = None

    # Form 8283 — Noncash Charitable Contributions
    form_8283_present: bool = False

    # Form 8889 — Health Savings Accounts
    form_8889_present: bool = False
    form_8889_hsa_contributions: Optional[float] = None
    form_8889_excess_contributions: Optional[float] = None

    # Form 7203 — S-Corp Basis Tracking
    form_7203_present: bool = False
    form_7203_stock_basis: Optional[float] = None
    form_7203_debt_basis: Optional[float] = None

    # Form 6198 — At-Risk Limitations
    form_6198_present: bool = False
    form_6198_at_risk_carryforward: Optional[float] = None

    # State returns
    state_returns_filed: List[str] = field(default_factory=list)

    # Elections & continuity indicators
    election_real_estate_professional: bool = False
    election_installment_sale: bool = False

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
class Form1099GData:
    """1099-G: Certain Government Payments (unemployment, state tax refunds)."""
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_unemployment_compensation: Optional[float] = None
    box2_state_local_tax_refund: Optional[float] = None
    box4_fed_withholding: Optional[float] = None
    box5_rtaa_payments: Optional[float] = None
    box6_taxable_grants: Optional[float] = None
    box7_agriculture_payments: Optional[float] = None
    box8_trade_or_business: bool = False
    box9_market_gain: Optional[float] = None
    box10a_state: Optional[str] = None
    box10b_state_id: Optional[str] = None
    box11_state_income_tax_withheld: Optional[float] = None
    is_corrected: bool = False
    confidence: float = 0.0
    extraction_source: str = "local"


@dataclass
class Form1099MISCData:
    """1099-MISC: Miscellaneous Information (rents, royalties, prizes, attorney fees)."""
    payer_name: Optional[str] = None
    payer_tin: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_rents: Optional[float] = None
    box2_royalties: Optional[float] = None
    box3_other_income: Optional[float] = None
    box4_fed_withholding: Optional[float] = None
    box5_fishing_boat_proceeds: Optional[float] = None
    box6_medical_payments: Optional[float] = None
    box7_direct_sales: bool = False
    box8_substitute_payments: Optional[float] = None
    box10_crop_insurance: Optional[float] = None
    box12_section_409a_deferrals: Optional[float] = None
    box14_gross_proceeds_attorney: Optional[float] = None
    box15_section_409a_income: Optional[float] = None
    box16_state_tax_withheld: Optional[float] = None
    box17_state_payer_no: Optional[str] = None
    box18_state_income: Optional[float] = None
    is_corrected: bool = False
    confidence: float = 0.0
    extraction_source: str = "local"


@dataclass
class Form1098TData:
    """1098-T: Tuition Statement (education credits — American Opportunity, Lifetime Learning)."""
    filer_name: Optional[str] = None
    filer_tin: Optional[str] = None
    student_name: Optional[str] = None
    student_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_payments_received: Optional[float] = None
    box4_adjustments_prior_year: Optional[float] = None
    box5_scholarships_grants: Optional[float] = None
    box6_adjustments_scholarships: Optional[float] = None
    box7_prior_year_amount: bool = False    # amounts include next Jan-Mar
    box8_half_time_student: bool = False
    box9_graduate_student: bool = False
    box10_insurance_reimbursements: Optional[float] = None
    is_corrected: bool = False
    confidence: float = 0.0
    extraction_source: str = "local"


@dataclass
class Form1099QData:
    """1099-Q: Payments from Qualified Education Programs (529 / Coverdell)."""
    payer_name: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_gross_distribution: Optional[float] = None
    box2_earnings: Optional[float] = None
    box3_basis: Optional[float] = None
    trustee_to_trustee: bool = False        # box 4 checkbox
    qualified_tuition_program: bool = False  # box 5 checkbox — Coverdell ESA if False
    is_corrected: bool = False
    confidence: float = 0.0
    extraction_source: str = "local"


@dataclass
class Form1099SAData:
    """1099-SA: Distributions from HSA, Archer MSA, or Medicare Advantage MSA."""
    payer_name: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_tin: Optional[str] = None
    account_number: Optional[str] = None
    year: Optional[int] = None
    box1_gross_distribution: Optional[float] = None
    box2_earnings_on_excess: Optional[float] = None
    box3_distribution_code: Optional[str] = None
    box4_fmv_on_date_of_death: Optional[float] = None
    box5_account_type: Optional[str] = None  # "HSA", "Archer MSA", or "Medicare Advantage MSA"
    is_corrected: bool = False
    confidence: float = 0.0
    extraction_source: str = "local"


@dataclass
class ExtractionResult:
    w2: List[W2Data] = field(default_factory=list)
    brokerage_1099: List[Brokerage1099Data] = field(default_factory=list)
    brokerage_1099_trades: List[Brokerage1099Trade] = field(default_factory=list)
    form_1098: List[Form1098Data] = field(default_factory=list)
    form_1099_nec: List[Form1099NECData] = field(default_factory=list)
    form_1099_r: List[Form1099RData] = field(default_factory=list)
    form_1099_g: List[Form1099GData] = field(default_factory=list)
    form_1099_misc: List[Form1099MISCData] = field(default_factory=list)
    form_1098_t: List[Form1098TData] = field(default_factory=list)
    form_1099_q: List[Form1099QData] = field(default_factory=list)
    form_1099_sa: List[Form1099SAData] = field(default_factory=list)
    unknown: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "w2": [asdict(item) for item in self.w2],
            "brokerage_1099": [asdict(item) for item in self.brokerage_1099],
            "brokerage_1099_trades": [asdict(item) for item in self.brokerage_1099_trades],
            "form_1098": [asdict(item) for item in self.form_1098],
            "form_1099_nec": [asdict(item) for item in self.form_1099_nec],
            "form_1099_r": [asdict(item) for item in self.form_1099_r],
            "form_1099_g": [asdict(item) for item in self.form_1099_g],
            "form_1099_misc": [asdict(item) for item in self.form_1099_misc],
            "form_1098_t": [asdict(item) for item in self.form_1098_t],
            "form_1099_q": [asdict(item) for item in self.form_1099_q],
            "form_1099_sa": [asdict(item) for item in self.form_1099_sa],
            "unknown": self.unknown,
        }
