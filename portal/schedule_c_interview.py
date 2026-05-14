"""
Schedule C (Profit or Loss From Business) interview configuration.
Multi-step guided interview for clients with self-employment income.
Each question carries help_text (client-facing), irs_ref (preparer-facing line/instruction),
pub_refs (IRS publication citations for preparer guidance panel), doc_hint (inline upload prompt),
and optional conditional visibility logic.
"""

# ---------------------------------------------------------------------------
# IRS instruction text snippets keyed by question key — shown in preparer
# guidance panel. Pulled from Schedule C instructions (2024 version).
# ---------------------------------------------------------------------------
IRS_INSTRUCTIONS = {
    "business_name": (
        "Enter the name of the proprietorship. If you are the sole owner of an LLC that is not treated "
        "as a corporation, enter the name of the LLC."
    ),
    "business_address": (
        "Enter the business address. Show a street address instead of a box number. Include the suite or "
        "room number, if any."
    ),
    "ein": (
        "Enter your employer identification number (EIN), if any. Do not enter your SSN. "
        "If you do not have an EIN, leave blank."
    ),
    "principal_activity": (
        "Describe the business or professional activity that provided your principal source of income "
        "reported on line 1. Give the general field or activity and the type of product or service."
    ),
    "naics_code": (
        "Enter the six-digit NAICS code that best describes your principal business activity. "
        "See Principal Business or Professional Activity Codes in the instructions."
    ),
    "accounting_method": (
        "Check the accounting method used to figure profit or loss. Cash method: report income in the year "
        "received and expenses in the year paid. Accrual method: report income when earned and expenses "
        "when incurred."
    ),
    "material_participation": (
        "You materially participated if you were involved in the operation of the activity on a regular, "
        "continuous, and substantial basis during the year. See the 7 tests in Pub. 925."
    ),
    "new_business": (
        "Check 'Yes' if you started or acquired this business in the current tax year."
    ),
    "issued_1099s": (
        "You must file Form(s) 1099 if, in the course of your trade or business, you paid $600 or more "
        "during the year to a person (not a corporation) for services. See the Instructions for Forms 1099."
    ),
    "gross_receipts": (
        "Line 1. Enter gross receipts from your trade or business. Include amounts you received in your "
        "trade or business that were properly shown on Forms 1099-NEC, 1099-MISC, and 1099-K. "
        "The amount on Form 1099-K may not represent the amount you must report as income."
    ),
    "returns_allowances": (
        "Line 2. Enter returns and allowances. Include cash or credit refunds you made to customers, "
        "rebates, and other allowances off the actual sales price."
    ),
    "other_income": (
        "Line 6. Enter on line 6 amounts from finance reserve income, scrap sales, bad debts you "
        "recovered, interest (including imputed interest) on notes and accounts receivable, state fuel "
        "tax refunds or credits, prizes and awards related to your business, and other kinds of "
        "miscellaneous business income."
    ),
    "advertising": (
        "Line 8. Enter the cost of any advertising for your business. Do not include advertising costs "
        "for a new business you are starting."
    ),
    "car_truck": (
        "Line 9. Enter the total amount of car and truck expenses for your business. If you claim car or "
        "truck expenses, you must complete Part IV (or attach Form 4562 if you are also depreciating "
        "assets other than the business vehicle)."
    ),
    "commissions_fees": (
        "Line 10. Enter commissions and fees paid to subcontractors or employees for the benefit of your "
        "business. Do not include contract labor here; see line 26."
    ),
    "contract_labor": (
        "Line 11. Enter amounts paid to subcontractors or independent contractors for services performed "
        "for your business. Do not include payments to employees (W-2 wages go on line 26). "
        "Generally, you must file Form 1099-NEC for each person to whom you paid $600 or more."
    ),
    "depletion": (
        "Line 12. Enter depletion claimed on oil, gas, or other mineral properties. See Pub. 535 "
        "for more information about depletion."
    ),
    "depreciation": (
        "Line 13. Enter the total depreciation and section 179 expense for business assets. If you are "
        "also depreciating assets placed in service before this year, you must complete Form 4562. "
        "Otherwise, you may compute the deduction yourself using the tables in Pub. 946."
    ),
    "employee_benefits": (
        "Line 14. Enter your contributions to employee benefit programs not included in line 19 "
        "(pension, profit-sharing). Examples: accident and health plans, group-term life insurance, "
        "and dependent care assistance programs."
    ),
    "insurance": (
        "Line 15. Enter premiums paid for business insurance. Do not include amounts paid for employee "
        "benefit programs (line 14) or your own health insurance deduction (Schedule 1, line 17)."
    ),
    "mortgage_interest": (
        "Line 16a. Enter mortgage interest paid to banks or other financial institutions. "
        "If you received a Form 1098, enter the interest shown on that form."
    ),
    "other_interest": (
        "Line 16b. Enter interest paid on other business loans. Do not include personal interest or "
        "interest on mortgages (line 16a)."
    ),
    "legal_professional": (
        "Line 17. Enter amounts paid to accountants, attorneys, and other professionals for services "
        "related to your business. Do not include amounts paid for personal services."
    ),
    "office_expense": (
        "Line 18. Enter the cost of office supplies and materials used in your business. "
        "Do not include postage — that is also deductible here. Computer software, equipment, and "
        "furniture generally must be depreciated (line 13)."
    ),
    "pension_profit_sharing": (
        "Line 19. Enter your deductible contributions to pension, profit-sharing, or annuity plans for "
        "your employees. If the plan covers you as a self-employed individual, see Pub. 560."
    ),
    "rent_vehicle": (
        "Line 20a. Enter amounts paid to rent or lease vehicles, machinery, or equipment for your "
        "business. If you leased a vehicle for more than 30 days, you may have to reduce this amount "
        "by an inclusion amount. See Pub. 463."
    ),
    "rent_other": (
        "Line 20b. Enter amounts paid to rent or lease real property used for your business. "
        "This includes office or workshop space."
    ),
    "repairs_maintenance": (
        "Line 21. Enter the cost of repairs and maintenance to keep your property in its normal "
        "operating condition. Do not include the cost of improvements (capitalized and depreciated)."
    ),
    "supplies": (
        "Line 22. Enter the cost of supplies not included in the cost of goods sold. This includes "
        "items used in your business that do not qualify as equipment. "
        "See the de minimis safe harbor in Regulations section 1.263(a)-1(f)."
    ),
    "taxes_licenses": (
        "Line 23. Enter taxes and licenses paid for your business. Include state and local sales taxes "
        "imposed on you as the seller of goods or services, employer share of FICA and Medicare, "
        "FUTA, state unemployment taxes, and personal property taxes on business assets."
    ),
    "travel": (
        "Line 24a. Enter the cost of transportation, lodging, and other travel expenses for overnight "
        "trips away from your tax home required by your business. Do not include meals. "
        "See Pub. 463 for substantiation requirements."
    ),
    "meals": (
        "Line 24b. Enter 50% of your deductible business meal expenses. Meals must have a business "
        "purpose, must not be lavish or extravagant, and you (or an employee) must be present. "
        "See Pub. 463."
    ),
    "utilities": (
        "Line 25. Enter the cost of heat, lights, power, telephone, and other utilities for your "
        "business location. If you use part of your home for business, use Form 8829 instead of "
        "listing home utilities here."
    ),
    "wages": (
        "Line 26. Enter the total wages paid to your employees (net of employment credits). "
        "Include salaries, hourly wages, and bonuses. Do not include payments to yourself."
    ),
    "home_office": (
        "Line 30. If you used part of your home for business, you may deduct expenses for the business "
        "use of your home. To qualify, you must use part of your home regularly and exclusively for "
        "your business. Use Form 8829 to compute the deduction (or the simplified method — $5/sq ft, "
        "max 300 sq ft = $1,500 max). See Pub. 587."
    ),
    "inventory_method": (
        "Line 33. Check the method you used to value closing inventory. Cost is the most common method "
        "for tax purposes. The lower-of-cost-or-market method may be used if inventory costs have "
        "declined. Small business taxpayers with average annual gross receipts of $31 million or less "
        "may use the overall cash method and are not required to maintain inventories."
    ),
    "beginning_inventory": (
        "Line 35. Enter the value of your inventory at the beginning of the tax year. "
        "This amount must match closing inventory on last year's Schedule C."
    ),
    "purchases": (
        "Line 36. Enter the cost of merchandise bought for sale. Subtract the cost of items withdrawn "
        "for personal use."
    ),
    "cost_of_labor": (
        "Line 37. Enter the cost of labor directly attributable to producing or buying the products "
        "you sell. Do not include your own labor."
    ),
    "materials_supplies_cogs": (
        "Line 38. Enter the cost of supplies and raw materials used directly in producing goods."
    ),
    "ending_inventory": (
        "Line 41. Enter the value of your inventory at the end of the tax year. "
        "You must use the same method of valuing inventory as on your prior-year return."
    ),
    "vehicle_date": (
        "Line 44a. Enter the date you first placed the vehicle in service for business. "
        "Only the business-use percentage of vehicle costs is deductible."
    ),
    "total_miles": (
        "Line 44b. Enter the total number of miles the vehicle was driven during the year."
    ),
    "business_miles": (
        "Line 44b. Enter the number of miles driven for business purposes. "
        "Commuting between home and regular work location is not deductible."
    ),
    "commuting_miles": (
        "Line 44b. Enter commuting miles (home to regular work location — not deductible)."
    ),
    "mileage_method": (
        "Line 44c. You can use the standard mileage rate (67¢/mile for 2024) instead of actual "
        "expenses. You must choose the standard rate in the first year you use the vehicle for "
        "business. See Pub. 463."
    ),
    "written_evidence": (
        "Line 47a. You must keep written records of the date, destination, business purpose, and "
        "mileage for each business trip. A mileage log, diary, or similar record is required "
        "to substantiate vehicle expenses. See Pub. 463."
    ),
    "personal_vehicle": (
        "Line 47b. Answer 'Yes' if you had another vehicle available for personal use. "
        "This helps establish that you used the listed vehicle primarily for business."
    ),
}

# ---------------------------------------------------------------------------
# Publication reference descriptions — shown in preparer sidebar
# ---------------------------------------------------------------------------
PUB_REFERENCES = {
    "334": "Tax Guide for Small Business (Pub. 334) — comprehensive overview of Schedule C",
    "463": "Travel, Gift, and Car Expenses (Pub. 463) — vehicle, meals, travel deduction rules",
    "587": "Business Use of Your Home (Pub. 587) — home office deduction, Form 8829",
    "946": "How To Depreciate Property (Pub. 946) — Section 179, bonus depreciation, MACRS tables",
    "535": "Business Expenses (Pub. 535) — detailed rules for all Schedule C expense categories",
    "560": "Retirement Plans for Small Business (Pub. 560) — SEP, SIMPLE, qualified plans",
    "925": "Passive Activity and At-Risk Rules (Pub. 925) — material participation tests",
    "538": "Accounting Periods and Methods (Pub. 538) — cash vs. accrual, inventory rules",
}

# ---------------------------------------------------------------------------
# Main interview structure
# ---------------------------------------------------------------------------
SCHEDULE_C_PARTS = [
    # ------------------------------------------------------------------
    {
        "id": "intro",
        "title": "Business Overview",
        "subtitle": "Tell us about your business",
        "questions": [
            {
                "key": "business_name",
                "label": "Business name (or your name if sole proprietor with no separate business name)",
                "type": "text",
                "required": True,
                "help_text": (
                    "Enter the legal name of your business. If you operate as an individual without a "
                    "formal business name, you can enter your own name."
                ),
                "irs_ref": "Schedule C, Name of proprietor / Business name",
                "pub_refs": ["334"],
            },
            {
                "key": "business_address",
                "label": "Business address (if different from your home address)",
                "type": "text",
                "required": False,
                "help_text": (
                    "Enter the street address where your business is located. Leave blank if you work "
                    "from home — your home address will be used."
                ),
                "irs_ref": "Schedule C, Business address",
                "pub_refs": ["334"],
            },
            {
                "key": "ein",
                "label": "Employer Identification Number (EIN), if any",
                "type": "text",
                "required": False,
                "help_text": (
                    "If you have a separate EIN for your business, enter it here. "
                    "If you operate under your Social Security Number only, leave this blank."
                ),
                "irs_ref": "Schedule C, Employer ID no.",
                "pub_refs": ["334"],
            },
            {
                "key": "principal_activity",
                "label": "Describe your principal business or professional activity",
                "type": "text",
                "required": True,
                "placeholder": "e.g., Freelance web design, Residential painting, Dog grooming",
                "help_text": (
                    "Briefly describe what your business does — the main product you sell or service "
                    "you provide. Be specific enough to identify your industry."
                ),
                "irs_ref": "Schedule C, Principal business or profession",
                "pub_refs": ["334"],
            },
            {
                "key": "naics_code",
                "label": "Business activity code (NAICS)",
                "type": "text",
                "required": False,
                "placeholder": "e.g., 541511",
                "help_text": (
                    "This is a 6-digit code that classifies your type of business. "
                    "Your tax preparer can help you find the right code — you can also look it up "
                    "in the IRS Schedule C instructions. It's okay to leave this blank for now."
                ),
                "irs_ref": "Schedule C, Business code",
                "pub_refs": ["334"],
            },
            {
                "key": "accounting_method",
                "label": "Accounting method",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "cash", "label": "Cash — I record income when received and expenses when paid"},
                    {"value": "accrual", "label": "Accrual — I record income when earned and expenses when incurred"},
                    {"value": "other", "label": "Other"},
                ],
                "help_text": (
                    "Most small businesses use the cash method: you report income in the year you "
                    "receive payment and deduct expenses in the year you pay them. "
                    "The accrual method is used when you bill clients and may not be paid immediately."
                ),
                "irs_ref": "Schedule C, Line F — Accounting method",
                "pub_refs": ["538"],
            },
            {
                "key": "material_participation",
                "label": "Did you materially participate in this business during the year?",
                "type": "yes_no",
                "required": True,
                "help_text": (
                    "Answer 'Yes' if you were actively involved in running the business on a regular "
                    "and ongoing basis — not just as a passive investor. Most self-employed people "
                    "answer 'Yes.' If you are unsure, talk to your preparer."
                ),
                "irs_ref": "Schedule C, Line G — Material participation",
                "pub_refs": ["925"],
            },
            {
                "key": "new_business",
                "label": "Did you start or acquire this business in the current tax year?",
                "type": "yes_no",
                "required": True,
                "help_text": (
                    "Answer 'Yes' if this is the first year you operated this business. "
                    "Startup costs may have special deduction rules."
                ),
                "irs_ref": "Schedule C, Line H — If you started or acquired this business...",
                "pub_refs": ["535"],
            },
            {
                "key": "issued_1099s",
                "label": "Did you make payments totaling $600 or more to any individual or unincorporated business for services?",
                "type": "yes_no",
                "required": True,
                "help_text": (
                    "If you paid a contractor, freelancer, or other individual $600+ for services "
                    "in the course of your business, you are generally required to issue them a "
                    "Form 1099-NEC. Answer 'Yes' if this applies to you."
                ),
                "irs_ref": "Schedule C, Line I — Did you make any payments that would require Form 1099?",
                "pub_refs": ["334"],
            },
            {
                "key": "filed_1099s",
                "label": "If yes, did you (or will you) file the required Form 1099s?",
                "type": "yes_no",
                "required": False,
                "conditional": {"key": "issued_1099s", "value": "yes"},
                "help_text": (
                    "The IRS asks this to confirm compliance. If you have not yet filed the 1099s, "
                    "let your preparer know — there may be a penalty for failure to file."
                ),
                "irs_ref": "Schedule C, Line J",
                "pub_refs": ["334"],
            },
        ],
        "doc_hints": [
            {
                "category": "EIN_Confirmation",
                "label": "EIN Confirmation Letter (CP 575)",
                "description": "IRS letter confirming your EIN (if applicable)",
                "trigger": None,
            },
            {
                "category": "Prior_Year_ScheduleC",
                "label": "Prior Year Schedule C",
                "description": "Last year's Schedule C for this business (helpful reference)",
                "trigger": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    {
        "id": "part1",
        "title": "Part I — Income",
        "subtitle": "Report all income from this business",
        "questions": [
            {
                "key": "gross_receipts",
                "label": "Gross receipts or sales — total income before any returns or expenses",
                "type": "money",
                "required": True,
                "help_text": (
                    "Enter all money your business took in during the year — cash, checks, credit card "
                    "payments, and any amounts reported on 1099-NEC, 1099-K, or 1099-MISC forms. "
                    "Include all income even if you haven't received payment for everything yet "
                    "(if using the accrual method)."
                ),
                "irs_ref": "Schedule C, Line 1 — Gross receipts or sales",
                "pub_refs": ["334"],
            },
            {
                "key": "returns_allowances",
                "label": "Returns and allowances (refunds given to customers)",
                "type": "money",
                "required": False,
                "help_text": (
                    "Enter the total of refunds, returns, or discounts you gave to customers during "
                    "the year. Leave blank or enter 0 if none."
                ),
                "irs_ref": "Schedule C, Line 2 — Returns and allowances",
                "pub_refs": ["334"],
            },
            {
                "key": "other_income",
                "label": "Other business income not included above",
                "type": "money",
                "required": False,
                "help_text": (
                    "Include any other income related to your business: interest on business bank "
                    "accounts, state fuel tax refunds, prizes and awards related to your work, "
                    "or income from incidental sales. Leave blank if none."
                ),
                "irs_ref": "Schedule C, Line 6 — Other income",
                "pub_refs": ["334"],
            },
        ],
        "doc_hints": [
            {
                "category": "1099_NEC",
                "label": "1099-NEC forms received",
                "description": "1099-NEC forms from each client who paid you $600 or more",
                "trigger": None,
            },
            {
                "category": "1099_K",
                "label": "1099-K (Payment Card / Third-Party Network)",
                "description": "1099-K from payment processors (PayPal, Stripe, Square, etc.)",
                "trigger": None,
            },
            {
                "category": "1099_MISC",
                "label": "1099-MISC (Other income)",
                "description": "1099-MISC for rents, royalties, or other miscellaneous income",
                "trigger": None,
            },
            {
                "category": "Business_Bank_Statements",
                "label": "Business bank statements",
                "description": "Full-year statements for all business checking/savings accounts",
                "trigger": None,
            },
        ],
    },

    # ------------------------------------------------------------------
    {
        "id": "part2",
        "title": "Part II — Expenses",
        "subtitle": "Deductible business expenses",
        "questions": [
            # --- Marketing & Professional ---
            {
                "key": "advertising",
                "label": "Advertising (online ads, print, flyers, website costs)",
                "type": "money",
                "required": False,
                "group": "Marketing & Professional",
                "help_text": (
                    "Enter amounts paid for business advertising: Google/Facebook ads, printed "
                    "materials, signage, business cards, or website hosting/domain fees. "
                    "Do not include costs for starting a new business."
                ),
                "irs_ref": "Schedule C, Line 8 — Advertising",
                "pub_refs": ["535"],
            },
            {
                "key": "legal_professional",
                "label": "Legal and professional services (accountants, attorneys, consultants)",
                "type": "money",
                "required": False,
                "group": "Marketing & Professional",
                "help_text": (
                    "Include fees paid to accountants (including tax preparation fees for this "
                    "business), attorneys, bookkeepers, and other professionals. "
                    "Do not include amounts for personal legal or financial services."
                ),
                "irs_ref": "Schedule C, Line 17 — Legal and professional services",
                "pub_refs": ["535"],
            },
            {
                "key": "office_expense",
                "label": "Office expense (supplies, postage, small items not capitalized)",
                "type": "money",
                "required": False,
                "group": "Marketing & Professional",
                "help_text": (
                    "Enter costs for paper, pens, printer ink, postage, and small office supplies. "
                    "Software subscriptions and computer equipment may go here if they cost less "
                    "than $2,500 (de minimis safe harbor) or can be depreciated on line 13."
                ),
                "irs_ref": "Schedule C, Line 18 — Office expense",
                "pub_refs": ["535"],
            },
            # --- People ---
            {
                "key": "contract_labor",
                "label": "Contract labor paid to independent contractors (subcontractors)",
                "type": "money",
                "required": False,
                "group": "People",
                "help_text": (
                    "Enter amounts paid to independent contractors or freelancers for work on your "
                    "business. If you paid any single person $600 or more, you should have issued "
                    "them a 1099-NEC. Do not include employee wages here."
                ),
                "irs_ref": "Schedule C, Line 11 — Contract labor",
                "pub_refs": ["334", "535"],
                "doc_hint": {
                    "category": "1099_NEC_Issued",
                    "label": "1099-NEC forms you issued to contractors",
                    "description": "Copies of 1099-NEC forms you sent to contractors you paid $600+",
                },
            },
            {
                "key": "wages",
                "label": "Wages paid to employees (W-2 wages, before employment credits)",
                "type": "money",
                "required": False,
                "group": "People",
                "help_text": (
                    "Enter gross wages, salaries, and bonuses paid to employees. "
                    "This amount should equal the total wages on your W-3 Transmittal. "
                    "Do not include wages you paid yourself."
                ),
                "irs_ref": "Schedule C, Line 26 — Wages (less employment credits)",
                "pub_refs": ["334", "535"],
                "doc_hint": {
                    "category": "Payroll_Records",
                    "label": "Payroll records / W-3 Transmittal",
                    "description": "W-3 and payroll summary showing total wages paid to employees",
                },
            },
            {
                "key": "employee_benefits",
                "label": "Employee benefit programs (health insurance, group life, dependent care)",
                "type": "money",
                "required": False,
                "group": "People",
                "help_text": (
                    "Enter contributions you made to employee benefit programs: accident and health "
                    "plans, group-term life insurance, dependent care assistance programs. "
                    "Do not include amounts for pension or profit-sharing plans (line 19)."
                ),
                "irs_ref": "Schedule C, Line 14 — Employee benefit programs",
                "pub_refs": ["535"],
            },
            {
                "key": "pension_profit_sharing",
                "label": "Pension and profit-sharing plan contributions for employees",
                "type": "money",
                "required": False,
                "group": "People",
                "help_text": (
                    "Enter contributions to qualified pension, profit-sharing, or SEP/SIMPLE plans "
                    "for your employees. For contributions for yourself, use Schedule 1 "
                    "(self-employed retirement deduction). See Pub. 560."
                ),
                "irs_ref": "Schedule C, Line 19 — Pension and profit-sharing plans",
                "pub_refs": ["560"],
            },
            # --- Assets & Depreciation ---
            {
                "key": "has_new_assets",
                "label": "Did you place any new assets in service for your business this year (equipment, machinery, furniture, technology)?",
                "type": "yes_no",
                "required": False,
                "group": "Assets & Depreciation",
                "help_text": (
                    "Answer 'Yes' if you bought or started using any equipment, machinery, furniture, "
                    "vehicles, or technology for your business this year. This triggers the "
                    "depreciation/Section 179 expense entry."
                ),
                "irs_ref": "Schedule C, Line 13 — Depreciation and section 179 expense",
                "pub_refs": ["946"],
            },
            {
                "key": "depreciation",
                "label": "Depreciation and Section 179 expense deduction for business assets",
                "type": "money",
                "required": False,
                "group": "Assets & Depreciation",
                "conditional": {"key": "has_new_assets", "value": "yes"},
                "help_text": (
                    "Enter the amount from Form 4562 (Depreciation and Amortization). "
                    "Section 179 lets you deduct the full cost of qualifying equipment in the year "
                    "you buy it, rather than depreciating it over several years. "
                    "Your preparer will calculate this from the asset list you provide."
                ),
                "irs_ref": "Schedule C, Line 13 — Depreciation and section 179",
                "pub_refs": ["946"],
                "doc_hint": {
                    "category": "Asset_List",
                    "label": "Asset purchase receipts / Asset list",
                    "description": "Invoices or receipts for new equipment, with purchase dates and costs",
                },
            },
            {
                "key": "repairs_maintenance",
                "label": "Repairs and maintenance",
                "type": "money",
                "required": False,
                "group": "Assets & Depreciation",
                "help_text": (
                    "Enter costs to keep business property in its normal working condition. "
                    "This includes labor and materials for minor repairs. "
                    "Do not include improvements that add value or extend the life of the property "
                    "(those must be capitalized and depreciated)."
                ),
                "irs_ref": "Schedule C, Line 21 — Repairs and maintenance",
                "pub_refs": ["535"],
            },
            {
                "key": "supplies",
                "label": "Supplies used in your business (not included in cost of goods sold)",
                "type": "money",
                "required": False,
                "group": "Assets & Depreciation",
                "help_text": (
                    "Enter the cost of supplies you used in your work that are not part of a "
                    "product you manufacture or sell. Examples: cleaning supplies, tools under "
                    "$2,500, packaging materials (if not in COGS)."
                ),
                "irs_ref": "Schedule C, Line 22 — Supplies",
                "pub_refs": ["535"],
            },
            # --- Financial ---
            {
                "key": "insurance",
                "label": "Business insurance premiums",
                "type": "money",
                "required": False,
                "group": "Financial",
                "help_text": (
                    "Enter premiums for business insurance: general liability, professional liability "
                    "(E&O), property, workers' comp, and similar policies. "
                    "Do not include health insurance for yourself — that is a separate deduction."
                ),
                "irs_ref": "Schedule C, Line 15 — Insurance (other than health)",
                "pub_refs": ["535"],
            },
            {
                "key": "mortgage_interest",
                "label": "Mortgage interest paid on business property (from Form 1098)",
                "type": "money",
                "required": False,
                "group": "Financial",
                "help_text": (
                    "If you own a business location and pay mortgage interest on it, enter the "
                    "amount from Form 1098. If you use part of your home for business, "
                    "use Form 8829 instead (home office section below)."
                ),
                "irs_ref": "Schedule C, Line 16a — Mortgage interest",
                "pub_refs": ["535"],
                "doc_hint": {
                    "category": "1098_Business",
                    "label": "Form 1098 — Business Mortgage Interest",
                    "description": "Form 1098 from your lender for business property mortgage interest",
                },
            },
            {
                "key": "other_interest",
                "label": "Other business interest expense (business loans, credit lines)",
                "type": "money",
                "required": False,
                "group": "Financial",
                "help_text": (
                    "Enter interest paid on business loans, lines of credit, or credit cards "
                    "used exclusively for business. Do not include personal credit card interest."
                ),
                "irs_ref": "Schedule C, Line 16b — Other interest",
                "pub_refs": ["535"],
            },
            {
                "key": "taxes_licenses",
                "label": "Taxes and licenses (business property tax, payroll taxes, licenses)",
                "type": "money",
                "required": False,
                "group": "Financial",
                "help_text": (
                    "Include: business personal property taxes, employer share of Social Security "
                    "and Medicare (FICA), FUTA, state unemployment (SUTA), business licenses "
                    "and permits. Do not include federal or state income taxes."
                ),
                "irs_ref": "Schedule C, Line 23 — Taxes and licenses",
                "pub_refs": ["535"],
            },
            {
                "key": "commissions_fees",
                "label": "Commissions and fees paid (not to employees or contractors)",
                "type": "money",
                "required": False,
                "group": "Financial",
                "help_text": (
                    "Enter commissions, referral fees, and similar payments made in connection "
                    "with your business. Do not include contract labor (line 11) or W-2 wages (line 26)."
                ),
                "irs_ref": "Schedule C, Line 10 — Commissions and fees",
                "pub_refs": ["535"],
            },
            # --- Travel & Meals ---
            {
                "key": "travel",
                "label": "Business travel (overnight trips — lodging and transportation, not meals)",
                "type": "money",
                "required": False,
                "group": "Travel & Meals",
                "help_text": (
                    "Enter the cost of business travel away from home overnight: airfare, hotel, "
                    "rental cars, and related transportation. Do not include meal costs here "
                    "(those go on the next line). Personal travel is not deductible."
                ),
                "irs_ref": "Schedule C, Line 24a — Travel",
                "pub_refs": ["463"],
            },
            {
                "key": "meals",
                "label": "Business meals (50% of actual cost — must have a business purpose)",
                "type": "money",
                "required": False,
                "group": "Travel & Meals",
                "help_text": (
                    "Enter 50% of your deductible business meal costs. To be deductible, meals "
                    "must have a clear business purpose, must not be lavish or extravagant, and "
                    "you or an employee must be present. Keep receipts showing who you met with "
                    "and the business purpose."
                ),
                "irs_ref": "Schedule C, Line 24b — Deductible meals",
                "pub_refs": ["463"],
            },
            # --- Rent & Utilities ---
            {
                "key": "rent_vehicle",
                "label": "Rent or lease — vehicles, machinery, or equipment",
                "type": "money",
                "required": False,
                "group": "Rent & Utilities",
                "help_text": (
                    "Enter amounts paid to rent or lease vehicles, tools, machinery, or equipment "
                    "used in your business. If you leased a car for more than 30 days, there may "
                    "be an 'inclusion amount' that reduces your deduction — ask your preparer."
                ),
                "irs_ref": "Schedule C, Line 20a — Rent/lease: vehicles, machinery, equipment",
                "pub_refs": ["463", "535"],
            },
            {
                "key": "rent_other",
                "label": "Rent or lease — office space, workshop, or other business property",
                "type": "money",
                "required": False,
                "group": "Rent & Utilities",
                "help_text": (
                    "Enter amounts paid to rent office space, a store, workshop, storage unit, "
                    "or other real property used in your business. "
                    "Do not include rent for your home (use the home office section instead)."
                ),
                "irs_ref": "Schedule C, Line 20b — Rent/lease: other business property",
                "pub_refs": ["535"],
            },
            {
                "key": "utilities",
                "label": "Utilities for your business location (not home office)",
                "type": "money",
                "required": False,
                "group": "Rent & Utilities",
                "help_text": (
                    "Enter utility costs for your business location: electricity, gas, water, "
                    "phone, and internet. If you work from home, do not enter home utilities "
                    "here — use the home office section below."
                ),
                "irs_ref": "Schedule C, Line 25 — Utilities",
                "pub_refs": ["535"],
            },
            # --- Home Office ---
            {
                "key": "home_office",
                "label": "Do you use part of your home regularly and exclusively for business?",
                "type": "yes_no",
                "required": True,
                "group": "Home Office",
                "help_text": (
                    "To claim a home office deduction, you must use a dedicated area of your home "
                    "exclusively and regularly for your business. It does not have to be a separate "
                    "room — a clearly defined workspace counts. It must be your principal place of "
                    "business (or where you meet clients)."
                ),
                "irs_ref": "Schedule C, Line 30 — Home office / Form 8829",
                "pub_refs": ["587"],
            },
            {
                "key": "home_office_method",
                "label": "Home office deduction method",
                "type": "select",
                "required": False,
                "group": "Home Office",
                "conditional": {"key": "home_office", "value": "yes"},
                "options": [
                    {"value": "simplified", "label": "Simplified ($5 per square foot, max 300 sq ft = $1,500 max)"},
                    {"value": "actual", "label": "Actual expenses (Form 8829 — proportion of home costs)"},
                ],
                "help_text": (
                    "The simplified method is easier: multiply the square footage of your dedicated "
                    "workspace (up to 300 sq ft) by $5. The actual expense method can yield a larger "
                    "deduction if your home expenses are high, but requires more documentation."
                ),
                "irs_ref": "Schedule C, Line 30 — Simplified method vs. Form 8829",
                "pub_refs": ["587"],
            },
            {
                "key": "home_office_sqft",
                "label": "Square footage used exclusively for business",
                "type": "number",
                "required": False,
                "group": "Home Office",
                "conditional": {"key": "home_office", "value": "yes"},
                "help_text": (
                    "Measure (or estimate) the area you use exclusively for your business. "
                    "For the simplified method, the maximum is 300 square feet."
                ),
                "irs_ref": "Form 8829, Line 1 / Simplified method calculation",
                "pub_refs": ["587"],
            },
            {
                "key": "home_total_sqft",
                "label": "Total square footage of your home",
                "type": "number",
                "required": False,
                "group": "Home Office",
                "conditional": {"key": "home_office_method", "value": "actual"},
                "help_text": (
                    "Enter the total finished square footage of your home. This is used to calculate "
                    "the business-use percentage on Form 8829."
                ),
                "irs_ref": "Form 8829, Line 2",
                "pub_refs": ["587"],
                "doc_hint": {
                    "category": "Home_Office_Docs",
                    "label": "Home office documentation",
                    "description": "Utility bills, mortgage statement, and property tax bill for home office calculation",
                },
            },
        ],
        "doc_hints": [],
    },

    # ------------------------------------------------------------------
    {
        "id": "part3",
        "title": "Part III — Cost of Goods Sold",
        "subtitle": "Only if your business manufactures, purchases, or sells products",
        "questions": [
            {
                "key": "has_inventory",
                "label": "Does your business involve producing, purchasing, or selling merchandise (physical goods)?",
                "type": "yes_no",
                "required": True,
                "help_text": (
                    "Answer 'Yes' if you sell physical products — whether you make them yourself "
                    "or buy and resell them. Answer 'No' if your business is purely service-based "
                    "(consulting, freelancing, etc.)."
                ),
                "irs_ref": "Schedule C, Part III — Cost of goods sold",
                "pub_refs": ["334", "538"],
            },
            {
                "key": "inventory_method",
                "label": "Inventory valuation method",
                "type": "select",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "options": [
                    {"value": "cost", "label": "Cost"},
                    {"value": "lower_of_cost_or_market", "label": "Lower of cost or market"},
                    {"value": "other", "label": "Other (explain to preparer)"},
                ],
                "help_text": (
                    "Most small businesses use 'cost' — you value inventory at what you paid for it. "
                    "You must use the same method every year. If you want to change methods, "
                    "IRS approval is required."
                ),
                "irs_ref": "Schedule C, Line 33 — Method used to value closing inventory",
                "pub_refs": ["538"],
            },
            {
                "key": "inventory_change",
                "label": "Did the method for valuing inventory change from last year?",
                "type": "yes_no",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "If you changed how you value your inventory from last year, the IRS needs to "
                    "know. This generally requires IRS consent and can affect your taxes. "
                    "Let your preparer know if the method changed."
                ),
                "irs_ref": "Schedule C, Line 34 — Was there any change in determining quantities...",
                "pub_refs": ["538"],
            },
            {
                "key": "beginning_inventory",
                "label": "Beginning inventory (value at start of tax year)",
                "type": "money",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "Enter the value of your inventory on January 1 (or the first day of your "
                    "fiscal year). This should match the ending inventory from your prior year "
                    "Schedule C. If this is your first year in business, enter 0."
                ),
                "irs_ref": "Schedule C, Line 35 — Inventory at beginning of year",
                "pub_refs": ["334"],
            },
            {
                "key": "purchases",
                "label": "Purchases of merchandise for resale (minus personal use withdrawals)",
                "type": "money",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "Enter the total cost of goods you bought for resale. Subtract the cost of any "
                    "items you withdrew for personal use. Do not include capital expenditures."
                ),
                "irs_ref": "Schedule C, Line 36 — Purchases less cost of items withdrawn for personal use",
                "pub_refs": ["334"],
            },
            {
                "key": "cost_of_labor",
                "label": "Cost of labor directly used to produce or purchase goods (not your own labor)",
                "type": "money",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "Enter wages and salaries paid directly to produce the goods you sell. "
                    "Do not include your own labor or wages deducted elsewhere."
                ),
                "irs_ref": "Schedule C, Line 37 — Cost of labor",
                "pub_refs": ["334"],
            },
            {
                "key": "materials_supplies_cogs",
                "label": "Materials and supplies used in production",
                "type": "money",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "Enter the cost of raw materials and supplies consumed in the production "
                    "of goods you sold. Do not duplicate amounts already in purchases (line 36)."
                ),
                "irs_ref": "Schedule C, Line 38 — Materials and supplies",
                "pub_refs": ["334"],
            },
            {
                "key": "ending_inventory",
                "label": "Ending inventory (value at end of tax year)",
                "type": "money",
                "required": False,
                "conditional": {"key": "has_inventory", "value": "yes"},
                "help_text": (
                    "Enter the value of your inventory on December 31 (or the last day of your "
                    "fiscal year). Count or estimate everything on hand. This amount will carry "
                    "forward as beginning inventory for next year."
                ),
                "irs_ref": "Schedule C, Line 41 — Inventory at end of year",
                "pub_refs": ["334"],
            },
        ],
        "doc_hints": [
            {
                "category": "Inventory_Records",
                "label": "Inventory records / purchase invoices",
                "description": "Physical inventory count records and purchase invoices for all goods",
                "trigger": {"key": "has_inventory", "value": "yes"},
            },
        ],
    },

    # ------------------------------------------------------------------
    {
        "id": "part4",
        "title": "Part IV — Vehicle Information",
        "subtitle": "Only if you used a vehicle for business",
        "questions": [
            {
                "key": "has_vehicle",
                "label": "Did you use a car or truck for your business during the year?",
                "type": "yes_no",
                "required": True,
                "help_text": (
                    "Answer 'Yes' if you drove a vehicle for business purposes — client visits, "
                    "supply runs, job sites, etc. Commuting between your home and a regular office "
                    "is not a business trip."
                ),
                "irs_ref": "Schedule C, Part IV — Information on Your Vehicle",
                "pub_refs": ["463"],
            },
            {
                "key": "vehicle_date",
                "label": "Date vehicle was first placed in service for business",
                "type": "date",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "Enter the date you first started using this vehicle for your business. "
                    "If it was before this tax year, enter the original in-service date."
                ),
                "irs_ref": "Schedule C, Line 44a — Date vehicle placed in service",
                "pub_refs": ["463"],
            },
            {
                "key": "total_miles",
                "label": "Total miles driven during the year (all purposes)",
                "type": "number",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "Enter the total miles driven for all purposes — business, commuting, and "
                    "personal. This is used to calculate your business-use percentage."
                ),
                "irs_ref": "Schedule C, Line 44b — Total miles",
                "pub_refs": ["463"],
            },
            {
                "key": "business_miles",
                "label": "Business miles driven (excluding commuting)",
                "type": "number",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "Enter miles driven specifically for business purposes. "
                    "Do not include commuting miles (home to regular office). "
                    "The 2024 standard mileage rate is 67 cents per mile."
                ),
                "irs_ref": "Schedule C, Line 44b — Business miles",
                "pub_refs": ["463"],
            },
            {
                "key": "commuting_miles",
                "label": "Commuting miles (home to regular work location — not deductible)",
                "type": "number",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "Enter miles driven between your home and your regular place of business. "
                    "These are not deductible. If your home is your principal place of business "
                    "(qualifying home office), you may not have any commuting miles."
                ),
                "irs_ref": "Schedule C, Line 44b — Commuting miles",
                "pub_refs": ["463"],
            },
            {
                "key": "mileage_method",
                "label": "Deduction method for vehicle expenses",
                "type": "select",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "options": [
                    {"value": "standard", "label": "Standard mileage rate (67¢/mile for 2024)"},
                    {"value": "actual", "label": "Actual expenses (gas, insurance, depreciation, repairs, etc.)"},
                ],
                "help_text": (
                    "The standard mileage rate is simpler — multiply business miles by 67¢. "
                    "Actual expenses require tracking all vehicle costs and applying the "
                    "business-use percentage. You must choose the standard rate in the first "
                    "year you use the vehicle for business if you want to use it in future years."
                ),
                "irs_ref": "Schedule C, Line 44c — Standard mileage rate vs. actual expenses",
                "pub_refs": ["463"],
            },
            {
                "key": "written_evidence",
                "label": "Do you have written records (mileage log or diary) to support your business mileage?",
                "type": "yes_no",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "The IRS requires contemporaneous written records to substantiate vehicle "
                    "expenses: date, destination, business purpose, and miles for each trip. "
                    "A mileage log app, diary, or calendar entries all qualify. "
                    "Without records, vehicle deductions may be disallowed on audit."
                ),
                "irs_ref": "Schedule C, Line 47a — Is there written evidence?",
                "pub_refs": ["463"],
                "doc_hint": {
                    "category": "Mileage_Log",
                    "label": "Mileage log",
                    "description": "Mileage log or calendar showing business trips with dates, destinations, and miles",
                },
            },
            {
                "key": "personal_vehicle",
                "label": "Do you have another vehicle available for personal use?",
                "type": "yes_no",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "This helps establish that you use the business vehicle primarily for business. "
                    "If this is your only vehicle, the IRS may scrutinize the business-use percentage."
                ),
                "irs_ref": "Schedule C, Line 47b — Another vehicle for personal use?",
                "pub_refs": ["463"],
            },
            {
                "key": "vehicle_off_duty",
                "label": "Was the vehicle available for personal use during off-duty hours?",
                "type": "yes_no",
                "required": False,
                "conditional": {"key": "has_vehicle", "value": "yes"},
                "help_text": (
                    "Answer based on whether employees (or you) could use the vehicle for personal "
                    "purposes outside of work hours. If employees have take-home vehicles, special "
                    "rules may apply."
                ),
                "irs_ref": "Schedule C, Line 46 — Vehicle available for personal use during off-duty hours?",
                "pub_refs": ["463"],
            },
        ],
        "doc_hints": [],
    },

    # ------------------------------------------------------------------
    {
        "id": "part5",
        "title": "Part V — Other Expenses",
        "subtitle": "Additional deductible expenses not listed above",
        "questions": [
            {
                "key": "other_expenses",
                "label": "List any other ordinary and necessary business expenses not already entered",
                "type": "other_expenses",
                "required": False,
                "help_text": (
                    "Enter any legitimate business expenses that don't fit the categories above. "
                    "Common examples: bank fees, dues and subscriptions, professional development "
                    "and education, software and tech tools, amortization of startup costs, "
                    "bad debts, uniforms, and safety equipment. "
                    "Each expense must be ordinary and necessary for your specific business."
                ),
                "irs_ref": "Schedule C, Part V — Other expenses (Lines 48a–48z)",
                "pub_refs": ["535"],
                "suggestions": [
                    "Bank fees and service charges",
                    "Professional dues and subscriptions",
                    "Continuing education and training",
                    "Software and technology subscriptions",
                    "Startup costs amortization",
                    "Bad debts (uncollectible business income)",
                    "Uniforms and work clothing (not suitable for everyday wear)",
                    "Tools and safety equipment (under $2,500)",
                    "Parking and tolls (business trips)",
                    "Professional licenses and certifications",
                ],
            },
        ],
        "doc_hints": [],
    },
]

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def get_all_questions() -> list[dict]:
    """Flat list of all questions across all parts."""
    questions = []
    for part in SCHEDULE_C_PARTS:
        questions.extend(part["questions"])
    return questions


def get_part_by_id(part_id: str) -> dict | None:
    for part in SCHEDULE_C_PARTS:
        if part["id"] == part_id:
            return part
    return None


def get_part_ids() -> list[str]:
    return [p["id"] for p in SCHEDULE_C_PARTS]


def get_inline_doc_hints(part_id: str, answers: dict) -> list[dict]:
    """
    Return all doc hints relevant for the given part, including per-question
    hints triggered by the current answers.
    """
    part = get_part_by_id(part_id)
    if not part:
        return []
    hints = []
    seen = set()

    def add_hint(h):
        cat = h.get("category")
        if cat and cat not in seen:
            seen.add(cat)
            hints.append(h)

    for q in part.get("questions", []):
        dh = q.get("doc_hint")
        if dh:
            cond = q.get("conditional")
            if cond:
                if answers.get(cond["key"]) == cond["value"]:
                    add_hint(dh)
            else:
                add_hint(dh)

    trigger_hints = part.get("doc_hints", [])
    for h in trigger_hints:
        trigger = h.get("trigger")
        if trigger:
            if answers.get(trigger["key"]) == trigger["value"]:
                add_hint(h)
        else:
            add_hint(h)

    return hints


def compute_net_profit(all_answers: dict) -> dict:
    """
    Compute Schedule C-style net profit/loss from stored answers across all parts.
    Returns a dict with line amounts and net_profit.
    """
    def money(key):
        try:
            return float(all_answers.get(key) or 0)
        except (ValueError, TypeError):
            return 0.0

    gross = money("gross_receipts") - money("returns_allowances")
    cogs = (
        money("beginning_inventory")
        + money("purchases")
        + money("cost_of_labor")
        + money("materials_supplies_cogs")
        - money("ending_inventory")
    )
    gross_profit = gross - cogs + money("other_income")

    total_expenses = sum(money(k) for k in [
        "advertising", "car_truck", "commissions_fees", "contract_labor",
        "depletion", "depreciation", "employee_benefits", "insurance",
        "mortgage_interest", "other_interest", "legal_professional",
        "office_expense", "pension_profit_sharing", "rent_vehicle",
        "rent_other", "repairs_maintenance", "supplies", "taxes_licenses",
        "travel", "meals", "utilities", "wages",
    ])

    # Add other expenses (list of {description, amount})
    other_exp_list = all_answers.get("other_expenses") or []
    if isinstance(other_exp_list, list):
        for item in other_exp_list:
            try:
                total_expenses += float(item.get("amount") or 0)
            except (ValueError, TypeError):
                pass

    net_profit = gross_profit - total_expenses
    return {
        "gross_receipts": money("gross_receipts"),
        "returns_allowances": money("returns_allowances"),
        "other_income": money("other_income"),
        "gross_income": gross,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
    }


def get_preparer_flags(all_answers: dict, summary: dict) -> list[dict]:
    """
    Return list of auto-detected issues/reminders for the preparer.
    Each flag: {level: 'warning'|'info', message: str}
    """
    flags = []

    if summary["net_profit"] < 0:
        flags.append({
            "level": "warning",
            "message": (
                f"Net loss of ${abs(summary['net_profit']):,.2f} — review at-risk rules (Pub. 925). "
                "Loss may be limited if taxpayer is not at risk for the full amount."
            ),
        })

    if all_answers.get("has_vehicle") == "yes":
        if all_answers.get("written_evidence") != "yes":
            flags.append({
                "level": "warning",
                "message": (
                    "Vehicle expenses claimed but written evidence not confirmed. "
                    "Advise client to provide mileage log — required for substantiation (Pub. 463)."
                ),
            })

    if all_answers.get("home_office") == "yes":
        if all_answers.get("home_office_method") == "actual":
            flags.append({
                "level": "info",
                "message": "Home office using actual expenses — Form 8829 required. Collect utility bills and mortgage/rent amounts.",
            })
        else:
            flags.append({
                "level": "info",
                "message": (
                    f"Home office: simplified method — "
                    f"{min(int(all_answers.get('home_office_sqft') or 0), 300)} sq ft × $5 = "
                    f"${min(int(all_answers.get('home_office_sqft') or 0), 300) * 5:,} deduction."
                ),
            })

    if all_answers.get("has_new_assets") == "yes" and not all_answers.get("depreciation"):
        flags.append({
            "level": "warning",
            "message": "New assets reported but depreciation/Section 179 amount not entered. Form 4562 will be needed.",
        })

    if all_answers.get("issued_1099s") == "yes" and all_answers.get("filed_1099s") != "yes":
        flags.append({
            "level": "warning",
            "message": "Taxpayer indicated payments requiring 1099s but has not confirmed filing. Verify 1099-NEC compliance.",
        })

    return flags
