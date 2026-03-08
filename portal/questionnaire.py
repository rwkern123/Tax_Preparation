"""
Form 13614-C based questionnaire sections and document mapping logic.
"""

QUESTIONNAIRE_SECTIONS = [
    {
        "id": "about_you",
        "title": "Section 1: About You",
        "questions": [
            {
                "id": "can_be_claimed",
                "label": "Can anyone claim you as a dependent on their tax return?",
                "type": "yes_no",
            },
            {
                "id": "tp_student",
                "label": "Were you a full-time student during the year?",
                "type": "yes_no",
            },
            {
                "id": "tp_blind",
                "label": "Were you blind?",
                "type": "yes_no",
            },
            {
                "id": "tp_disabled",
                "label": "Were you disabled?",
                "type": "yes_no",
            },
            {
                "id": "tp_us_citizen",
                "label": "Are you a US citizen or resident alien?",
                "type": "yes_no",
            },
            {
                "id": "tp_foreign_accounts",
                "label": "Did you have a foreign financial account?",
                "type": "yes_no",
            },
        ],
    },
    {
        "id": "about_spouse",
        "title": "Section 2: About Your Spouse",
        "spouse_only": True,
        "questions": [
            {
                "id": "sp_student",
                "label": "Was your spouse a full-time student?",
                "type": "yes_no",
            },
            {
                "id": "sp_blind",
                "label": "Was your spouse blind?",
                "type": "yes_no",
            },
            {
                "id": "sp_disabled",
                "label": "Was your spouse disabled?",
                "type": "yes_no",
            },
            {
                "id": "sp_us_citizen",
                "label": "Is your spouse a US citizen or resident alien?",
                "type": "yes_no",
            },
        ],
    },
    {
        "id": "dependents",
        "title": "Section 3: Dependents",
        "questions": [
            {
                "id": "has_dependents",
                "label": "Do you have any dependents to claim?",
                "type": "yes_no",
            },
            {
                "id": "dependents_list",
                "label": "List your dependents",
                "type": "dependents",
                "show_if": {"question": "has_dependents", "value": "yes"},
            },
        ],
    },
    {
        "id": "income",
        "title": "Section 4: Income",
        "questions": [
            {
                "id": "tp_wages",
                "label": "Did you receive wages (W-2) from an employer?",
                "type": "yes_no",
            },
            {
                "id": "sp_wages",
                "label": "Did your spouse receive wages (W-2) from an employer?",
                "type": "yes_no",
                "show_if": {"question": "_married", "value": "yes"},
            },
            {
                "id": "tip_income",
                "label": "Did you receive tip income?",
                "type": "yes_no",
            },
            {
                "id": "interest_income",
                "label": "Did you receive interest income (1099-INT)?",
                "type": "yes_no",
            },
            {
                "id": "dividend_income",
                "label": "Did you receive dividend income (1099-DIV)?",
                "type": "yes_no",
            },
            {
                "id": "state_refund",
                "label": "Did you receive a state or local tax refund (1099-G)?",
                "type": "yes_no",
            },
            {
                "id": "alimony_received",
                "label": "Did you receive alimony? (Only applies to divorces finalized before 1/1/2019)",
                "type": "yes_no",
            },
            {
                "id": "self_employment",
                "label": "Did you have self-employment or business income?",
                "type": "yes_no",
            },
            {
                "id": "farm_income",
                "label": "Did you have farm income?",
                "type": "yes_no",
            },
            {
                "id": "rental_income",
                "label": "Did you have rental or royalty income?",
                "type": "yes_no",
            },
            {
                "id": "k1_income",
                "label": "Did you receive a Schedule K-1 (partnership, S-corp, trust, or estate)?",
                "type": "yes_no",
            },
            {
                "id": "gambling_income",
                "label": "Did you have gambling winnings (W-2G)?",
                "type": "yes_no",
            },
            {
                "id": "ira_pension",
                "label": "Did you receive IRA or pension distributions (1099-R)?",
                "type": "yes_no",
            },
            {
                "id": "social_security",
                "label": "Did you receive Social Security or Railroad Retirement benefits?",
                "type": "yes_no",
            },
            {
                "id": "unemployment",
                "label": "Did you receive unemployment compensation (1099-G)?",
                "type": "yes_no",
            },
            {
                "id": "investments_sold",
                "label": "Did you sell stocks, bonds, or other investments (1099-B)?",
                "type": "yes_no",
            },
            {
                "id": "home_sold",
                "label": "Did you sell your home or other real estate?",
                "type": "yes_no",
            },
            {
                "id": "crypto",
                "label": "Did you receive, sell, exchange, or otherwise dispose of any cryptocurrency?",
                "type": "yes_no",
            },
            {
                "id": "foreign_income",
                "label": "Did you have any foreign income?",
                "type": "yes_no",
            },
            {
                "id": "other_income",
                "label": "Did you have any other income not listed above?",
                "type": "yes_no",
            },
        ],
    },
    {
        "id": "deductions",
        "title": "Section 5: Deductions & Credits",
        "questions": [
            {
                "id": "alimony_paid",
                "label": "Did you pay alimony? (Only applies to divorces finalized before 1/1/2019)",
                "type": "yes_no",
            },
            {
                "id": "educator",
                "label": "Were you (or spouse) a K-12 teacher or educator?",
                "type": "yes_no",
            },
            {
                "id": "college_expenses",
                "label": "Did you or a dependent attend college or vocational school?",
                "type": "yes_no",
            },
            {
                "id": "student_loan_interest",
                "label": "Did you pay student loan interest?",
                "type": "yes_no",
            },
            {
                "id": "hsa",
                "label": "Did you have a Health Savings Account (HSA)?",
                "type": "yes_no",
            },
            {
                "id": "ira_contribution",
                "label": "Did you contribute to a traditional IRA?",
                "type": "yes_no",
            },
            {
                "id": "mortgage",
                "label": "Did you pay mortgage interest on your home?",
                "type": "yes_no",
            },
            {
                "id": "real_estate_taxes",
                "label": "Did you pay real estate taxes?",
                "type": "yes_no",
            },
            {
                "id": "charitable",
                "label": "Did you make charitable contributions?",
                "type": "yes_no",
            },
            {
                "id": "medical_expenses",
                "label": "Did you have significant medical or dental expenses?",
                "type": "yes_no",
            },
            {
                "id": "child_care",
                "label": "Did you pay for child or dependent care?",
                "type": "yes_no",
            },
            {
                "id": "estimated_payments",
                "label": "Did you make federal or state estimated tax payments?",
                "type": "yes_no",
            },
            {
                "id": "energy_improvements",
                "label": "Did you make energy-efficient home improvements?",
                "type": "yes_no",
            },
            {
                "id": "casualty_loss",
                "label": "Did you have a casualty or theft loss from a federally declared disaster?",
                "type": "yes_no",
            },
        ],
    },
    {
        "id": "life_events",
        "title": "Section 6: Life Events",
        "questions": [
            {
                "id": "married_this_year",
                "label": "Did you get married or divorced this year?",
                "type": "yes_no",
            },
            {
                "id": "new_dependent",
                "label": "Did you have a baby, adopt a child, or have a new dependent this year?",
                "type": "yes_no",
            },
            {
                "id": "bought_home",
                "label": "Did you buy or sell a home this year?",
                "type": "yes_no",
            },
            {
                "id": "marketplace_insurance",
                "label": "Did you or anyone in your household have health insurance through the Marketplace (ACA/Healthcare.gov)?",
                "type": "yes_no",
            },
            {
                "id": "no_health_insurance",
                "label": "Was there any period this year when you (or a family member) did not have health insurance?",
                "type": "yes_no",
            },
            {
                "id": "identity_pin",
                "label": "Did you receive an Identity Protection PIN (IP PIN) from the IRS?",
                "type": "yes_no",
            },
        ],
    },
]


def get_required_documents(answers: dict, filing_status: str) -> list[dict]:
    """
    Return a list of required document dicts based on questionnaire answers and filing status.
    Each dict: {"category": str, "label": str, "description": str, "required": bool}
    """
    docs = []
    seen_categories = set()

    def add(category: str, label: str, description: str, required: bool = True):
        if category not in seen_categories:
            seen_categories.add(category)
            docs.append({
                "category": category,
                "label": label,
                "description": description,
                "required": required,
            })

    # Always required
    add("Prior_Year_Return", "Prior Year Tax Return",
        "Copy of last year's federal and state returns (for reference)")
    add("ID", "Photo ID",
        "Government-issued photo ID for taxpayer (and spouse if applicable)")

    # Income
    if answers.get("tp_wages") == "yes":
        add("W2_Taxpayer", "W-2 (Taxpayer)",
            "Wage statement from each employer")

    if answers.get("sp_wages") == "yes":
        add("W2_Spouse", "W-2 (Spouse)",
            "Wage statement from each employer (spouse)")

    if answers.get("interest_income") == "yes":
        add("1099_INT", "1099-INT",
            "Interest income statements from banks/brokerages")

    if answers.get("dividend_income") == "yes":
        add("1099_DIV", "1099-DIV",
            "Dividend income statements")

    if answers.get("investments_sold") == "yes" or answers.get("crypto") == "yes":
        add("1099_B", "1099-B / Brokerage Statement",
            "Investment sale records, trade confirmations, crypto transaction history")

    if answers.get("ira_pension") == "yes":
        add("1099_R", "1099-R",
            "IRA or pension distribution statements")

    if answers.get("social_security") == "yes":
        add("SSA_1099", "SSA-1099 or RRB-1099",
            "Social Security or Railroad Retirement benefit statement")

    if answers.get("unemployment") == "yes":
        add("1099_G_Unemployment", "1099-G (Unemployment)",
            "Unemployment compensation statement")

    if answers.get("state_refund") == "yes":
        add("1099_G_Refund", "1099-G (State Refund)",
            "State or local tax refund statement")

    if answers.get("self_employment") == "yes":
        add("1099_NEC", "1099-NEC / Business Records",
            "Self-employment income (1099-NEC, 1099-MISC) and all business expense records")

    if answers.get("farm_income") == "yes":
        add("Farm_Records", "Farm Income & Expense Records",
            "All farm income and expense documentation")

    if answers.get("rental_income") == "yes":
        add("Rental_Records", "Rental Income & Expense Records",
            "Rental income received and all rental property expenses")

    if answers.get("k1_income") == "yes":
        add("K1", "Schedule K-1",
            "K-1 from partnerships, S-corporations, trusts, or estates")

    if answers.get("gambling_income") == "yes":
        add("W2G", "W-2G",
            "Gambling winnings statements")

    # Deductions & Credits
    if answers.get("mortgage") == "yes":
        add("1098", "1098 (Mortgage Interest)",
            "Mortgage interest statement from lender")

    if answers.get("college_expenses") == "yes":
        add("1098_T", "1098-T (Tuition)",
            "Tuition statement from college or vocational school")

    if answers.get("student_loan_interest") == "yes":
        add("1098_E", "1098-E (Student Loan)",
            "Student loan interest statement")

    if answers.get("marketplace_insurance") == "yes":
        add("1095_A", "1095-A (Marketplace Insurance)",
            "Health Insurance Marketplace Statement")

    if answers.get("hsa") == "yes":
        add("HSA_1099SA", "1099-SA / 5498-SA (HSA)",
            "HSA distribution and contribution statements")

    if answers.get("child_care") == "yes":
        add("Childcare_Records", "Childcare Provider Information",
            "Provider name, address, EIN/SSN, and amounts paid for each provider")

    if answers.get("charitable") == "yes":
        add("Charitable_Records", "Charitable Contribution Records",
            "Receipts or acknowledgment letters for all cash and non-cash donations")

    if answers.get("estimated_payments") == "yes":
        add("Estimated_Tax", "Estimated Tax Payment Records",
            "Amounts and dates of federal and state estimated payments made")

    if answers.get("home_sold") == "yes":
        add("1099_S", "1099-S / Closing Documents",
            "Sale proceeds statement and closing documents for real estate sold")

    if answers.get("bought_home") == "yes":
        add("Home_Purchase", "Home Purchase Documents",
            "Closing disclosure/HUD-1 for home purchased")

    if answers.get("foreign_income") == "yes" or answers.get("tp_foreign_accounts") == "yes":
        add("Foreign_Accounts", "Foreign Income / Account Records",
            "Foreign income records, FBAR filing info, Form 8938 data")

    if answers.get("identity_pin") == "yes":
        add("IP_PIN", "IRS Identity Protection PIN",
            "Your IP PIN letter from the IRS")

    if answers.get("ira_contribution") == "yes":
        add("IRA_Contribution", "IRA Contribution Records",
            "Records of IRA contributions made during the year (Form 5498)")

    if answers.get("energy_improvements") == "yes":
        add("Energy_Credits", "Energy Improvement Receipts",
            "Receipts and manufacturer certifications for energy-efficient home improvements")

    if answers.get("casualty_loss") == "yes":
        add("Casualty_Loss", "Casualty/Theft Loss Documentation",
            "Insurance claims, appraisals, and documentation of losses from disasters or theft")

    return docs


def get_section_for_filing_status(sections: list[dict], filing_status: str) -> list[dict]:
    """Filter sections based on filing status (hide spouse section if not married)."""
    is_married = filing_status in ("mfj", "mfs", "married_filing_jointly", "married_filing_separately")
    result = []
    for section in sections:
        if section.get("spouse_only") and not is_married:
            continue
        result.append(section)
    return result
