import unittest

from src.classify import classify_document
from pathlib import Path

from src.extract.schedule_c import parse_schedule_c_text


SAMPLE_FILLED_SCHEDULE_C = """
SCHEDULE C Profit or Loss From Business OMB No. 1545-0074
(Form 1040) (Sole Proprietorship) 2024
Department of the Treasury Attach to Form 1040, 1040-SR, 1040-SS, 1040-NR, or 1041
Internal Revenue Service Go to www.irs.gov/ScheduleC for instructions
Name of proprietor Social security number (SSN)
Jane Q. Consultant 123-45-6789
A Principal business or profession, including product or service B Enter code from instructions
Management consulting services 541610
C Business name. If no separate business name, leave blank. D Employer ID number (EIN)
Acme Advisory LLC 12-3456789
E Business address (including suite or room no.)
1234 Market Street Suite 500
City, town or post office, state, and ZIP code
San Francisco, CA 94103
F Accounting method: (1) [X] Cash (2) Accrual (3) Other (specify)
G Did you "materially participate" in the operation of this business during 2024? Yes [X]  No
H If you started or acquired this business during 2024, check here .
I Did you make any payments in 2024 that would require you to file Form(s) 1099? Yes [X]  No
J If "Yes," did you or will you file required Form(s) 1099? Yes [X]  No
Part I Income
1 Gross receipts or sales. See instructions for line 1 1 285,400.00
2 Returns and allowances 2 1,200.00
3 Subtract line 2 from line 1 3 284,200.00
4 Cost of goods sold (from line 42) 4 0.00
5 Gross profit. Subtract line 4 from line 3 5 284,200.00
6 Other income, including federal and state gasoline or fuel tax credit or refund 6 0.00
7 Gross income. Add lines 5 and 6 7 284,200.00
Part II Expenses. Enter expenses for business use of your home only on line 30.
8 Advertising 8 4,500.00
9 Car and truck expenses (see instructions) 9 8,200.00
10 Commissions and fees 10 0.00
11 Contract labor (see instructions) 11 24,000.00
12 Depletion 12 0.00
13 Depreciation and section 179 expense deduction 13 6,500.00
14 Employee benefit programs 14 0.00
15 Insurance (other than health) 15 1,800.00
16 Interest:
a Mortgage (paid to banks, etc.) 16a 0.00
b Other 16b 250.00
17 Legal and professional services 17 3,200.00
18 Office expense (see instructions) 18 1,400.00
19 Pension and profit-sharing plans 19 0.00
20 Rent or lease (see instructions):
a Vehicles, machinery, and equipment 20a 0.00
b Other business property 20b 18,000.00
21 Repairs and maintenance 21 600.00
22 Supplies (not included in Part III) 22 2,100.00
23 Taxes and licenses 23 1,250.00
24 Travel and meals:
a Travel 24a 5,400.00
b Deductible meals (see instructions) 24b 1,800.00
25 Utilities 25 2,400.00
26 Wages (less employment credits) 26 0.00
27 a Energy efficient commercial bldgs deduction (attach Form 7205) 27a 0.00
b Other expenses (from line 48) 27b 3,200.00
28 Total expenses before expenses for business use of home. Add lines 8 through 27b 28 84,600.00
29 Tentative profit or (loss). Subtract line 28 from line 7 29 199,600.00
30 Expenses for business use of your home. 30 1,500.00
31 Net profit or (loss). Subtract line 30 from line 29 31 198,100.00
32 If you have a loss, check the box that describes your investment in this activity.
32a [X] All investment is at risk.
32b Some investment is not at risk.
"""


SAMPLE_PART_III_IV_V = """
Part III Cost of Goods Sold (see instructions)
33 Method(s) used to value closing inventory: a [X] Cost b Lower of cost or market c Other
34 Was there any change in determining quantities, costs, or valuations? Yes  No [X]
35 Inventory at beginning of year 35 12,000.00
36 Purchases less cost of items withdrawn for personal use 36 45,000.00
37 Cost of labor 37 8,000.00
38 Materials and supplies 38 2,500.00
39 Other costs 39 0.00
40 Add lines 35 through 39 40 67,500.00
41 Inventory at end of year 41 14,200.00
42 Cost of goods sold. Subtract line 41 from line 40 42 53,300.00
Part IV Information on Your Vehicle.
43 When did you place your vehicle in service for business purposes? 03/15/2022
44 Of the total number of miles you drove your vehicle during 2024:
a Business 8,500 b Commuting 2,400 c Other 3,100
45 Was your vehicle available for personal use during off-duty hours? Yes [X]  No
46 Do you (or your spouse) have another vehicle available for personal use? Yes  No [X]
47a Do you have evidence to support your deduction? Yes [X]  No
b If "Yes," is the evidence written? Yes [X]  No
Part V Other Expenses. List below business expenses not included on lines 8-27a, or line 30.
Subscriptions and dues 1,200.00
Continuing education 800.00
Bank service charges 350.00
Software licenses 850.00
48 Total other expenses. Enter here and on line 27b 48 3,200.00
"""


class TestParseScheduleC(unittest.TestCase):
    def test_header_fields(self):
        data = parse_schedule_c_text(SAMPLE_FILLED_SCHEDULE_C)
        self.assertEqual(data.year, 2024)
        self.assertEqual(data.proprietor_name, "Jane Q. Consultant")
        self.assertEqual(data.proprietor_ssn, "123-45-6789")
        self.assertEqual(data.line_a_principal_business, "Management consulting services")
        self.assertEqual(data.line_b_business_code, "541610")
        self.assertEqual(data.line_c_business_name, "Acme Advisory LLC")
        self.assertEqual(data.line_d_ein, "12-3456789")
        self.assertEqual(data.line_f_accounting_method, "cash")
        self.assertTrue(data.line_g_material_participation)
        self.assertTrue(data.line_i_made_payments_requiring_1099)
        self.assertTrue(data.line_j_filed_required_1099)

    def test_part_i_income(self):
        data = parse_schedule_c_text(SAMPLE_FILLED_SCHEDULE_C)
        self.assertEqual(data.line_1_gross_receipts, 285400.00)
        self.assertEqual(data.line_2_returns_allowances, 1200.00)
        self.assertEqual(data.line_3_net_receipts, 284200.00)
        self.assertEqual(data.line_5_gross_profit, 284200.00)
        self.assertEqual(data.line_7_gross_income, 284200.00)

    def test_part_ii_expenses(self):
        data = parse_schedule_c_text(SAMPLE_FILLED_SCHEDULE_C)
        self.assertEqual(data.line_8_advertising, 4500.00)
        self.assertEqual(data.line_9_car_truck, 8200.00)
        self.assertEqual(data.line_11_contract_labor, 24000.00)
        self.assertEqual(data.line_13_depreciation_section_179, 6500.00)
        self.assertEqual(data.line_15_insurance, 1800.00)
        self.assertEqual(data.line_16b_other_interest, 250.00)
        self.assertEqual(data.line_17_legal_professional, 3200.00)
        self.assertEqual(data.line_18_office_expense, 1400.00)
        self.assertEqual(data.line_20b_rent_other_property, 18000.00)
        self.assertEqual(data.line_22_supplies, 2100.00)
        self.assertEqual(data.line_23_taxes_licenses, 1250.00)
        self.assertEqual(data.line_24a_travel, 5400.00)
        self.assertEqual(data.line_24b_meals, 1800.00)
        self.assertEqual(data.line_25_utilities, 2400.00)
        self.assertEqual(data.line_27b_other_expenses, 3200.00)
        self.assertEqual(data.line_28_total_expenses, 84600.00)
        self.assertEqual(data.line_29_tentative_profit_loss, 199600.00)
        self.assertEqual(data.line_30_home_office, 1500.00)
        self.assertEqual(data.line_31_net_profit_loss, 198100.00)
        self.assertTrue(data.line_32a_all_at_risk)
        self.assertFalse(data.line_32b_some_not_at_risk)

    def test_part_iii_cogs(self):
        data = parse_schedule_c_text(SAMPLE_PART_III_IV_V)
        self.assertEqual(data.line_33_inventory_method, "cost")
        self.assertFalse(data.line_34_inventory_method_change)
        self.assertEqual(data.line_35_inventory_beginning, 12000.00)
        self.assertEqual(data.line_36_purchases, 45000.00)
        self.assertEqual(data.line_37_cost_of_labor, 8000.00)
        self.assertEqual(data.line_38_materials_supplies, 2500.00)
        self.assertEqual(data.line_40_total_inputs, 67500.00)
        self.assertEqual(data.line_41_inventory_end, 14200.00)
        self.assertEqual(data.line_42_cogs, 53300.00)

    def test_part_iv_vehicle(self):
        data = parse_schedule_c_text(SAMPLE_PART_III_IV_V)
        self.assertEqual(data.line_43_date_placed_in_service, "03/15/2022")
        self.assertEqual(data.line_44a_business_miles, 8500.0)
        self.assertEqual(data.line_44b_commuting_miles, 2400.0)
        self.assertEqual(data.line_44c_other_miles, 3100.0)
        self.assertTrue(data.line_45_personal_use_offduty)
        self.assertFalse(data.line_46_another_vehicle_personal)
        self.assertTrue(data.line_47a_evidence_to_support)
        self.assertTrue(data.line_47b_evidence_written)

    def test_part_v_other_expenses(self):
        data = parse_schedule_c_text(SAMPLE_PART_III_IV_V)
        self.assertEqual(data.line_48_total_other_expenses, 3200.00)
        descriptions = [item["description"] for item in data.other_expenses_items]
        self.assertIn("Subscriptions and dues", descriptions)
        self.assertIn("Continuing education", descriptions)
        amounts = [item["amount"] for item in data.other_expenses_items]
        self.assertIn(1200.00, amounts)
        self.assertIn(850.00, amounts)

    def test_loss_with_at_risk_box(self):
        text_loss = SAMPLE_FILLED_SCHEDULE_C.replace(
            "31 Net profit or (loss). Subtract line 30 from line 29 31 198,100.00",
            "31 Net profit or (loss). Subtract line 30 from line 29 31 (12,500.00)",
        ).replace(
            "32a [X] All investment is at risk.",
            "32a All investment is at risk.",
        ).replace(
            "32b Some investment is not at risk.",
            "32b [X] Some investment is not at risk.",
        )
        data = parse_schedule_c_text(text_loss)
        self.assertEqual(data.line_31_net_profit_loss, -12500.00)
        self.assertTrue(data.line_32b_some_not_at_risk)

    def test_confidence_for_filled_form(self):
        data = parse_schedule_c_text(SAMPLE_FILLED_SCHEDULE_C)
        self.assertGreaterEqual(data.confidence, 0.85)

    def test_blank_form_low_confidence(self):
        # Confirm a blank form (e.g. the unfilled IRS PDF) yields zero or near-zero confidence
        blank_text = "SCHEDULE C Profit or Loss From Business 2025 (Sole Proprietorship)\n"
        data = parse_schedule_c_text(blank_text)
        self.assertEqual(data.confidence, 0.0)


class TestScheduleCClassification(unittest.TestCase):
    def test_classifies_filled_schedule_c(self):
        # Use a non-existent path; classify_document only inspects text + filename
        path = Path("/tmp/sample_schedule_c.pdf")
        doc_type, confidence, year = classify_document(path, SAMPLE_FILLED_SCHEDULE_C)
        self.assertEqual(doc_type, "schedule_c")
        self.assertGreaterEqual(confidence, 0.5)
        self.assertEqual(year, 2024)


if __name__ == "__main__":
    unittest.main()
