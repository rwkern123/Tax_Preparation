import unittest

from src.extract.brokerage_1099 import parse_brokerage_1099_text
from src.extract.form_1098 import parse_1098_text
from src.extract.w2 import parse_w2_text


class TestParsers(unittest.TestCase):
    def test_parse_w2(self):
        text = """
        Form W-2 2024
        Employer's name: ABC Corp
        EIN 12-3456789
        Box 1 Wages 85,200.00
        Box 2 Federal income tax withheld 12,900.00
        Box 12 D 6,000.00
        Box 16 State wages 85,200.00
        Box 17 State income tax 4,100.00
        NY
        """
        data = parse_w2_text(text)
        self.assertEqual(data.employer_ein, "12-3456789")
        self.assertEqual(data.box1_wages, 85200.00)
        self.assertIn("D", data.box12)
        self.assertIn("NY", data.states)

    def test_parse_brokerage(self):
        text = """
        Broker: Fidelity
        2024 Composite Statement
        Ordinary dividends 1,250.00
        Qualified dividends 900.00
        Interest income 210.00
        Foreign tax paid 35.00
        Total proceeds 10,000.00
        Cost basis 8,200.00
        Wash sale 125.00
        """
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.broker_name, "Fidelity")
        self.assertEqual(data.div_ordinary, 1250.00)
        self.assertEqual(data.b_summary["wash_sales"], 125.00)

    def test_parse_1098(self):
        text = """
        Form 1098 Mortgage Interest Statement 2024
        Lender name: Wells Fargo Home Mortgage
        Payer name: Ryan Kern
        1. Mortgage interest received 7,200.00
        2. Outstanding mortgage principal 450,000.00
        5. Mortgage insurance premiums 0.00
        6. Points paid on purchase of principal residence 0.00
        10. Real estate taxes 3,500.00
        """
        data = parse_1098_text(text)
        self.assertEqual(data.payer_name, "Ryan Kern")
        self.assertEqual(data.mortgage_interest_received, 7200.00)
        self.assertEqual(data.real_estate_taxes, 3500.00)


    def test_parse_w2_ocr_variants(self):
        text = """
        Form W-2 2024
        Employer name ACME LLC
        EIN 98-7654321
        Box I Wages $85,200.00
        Box 2 Federa1 income tax withheld 12,900
        12 D (6,000.00)
        """
        data = parse_w2_text(text)
        self.assertEqual(data.box1_wages, 85200.00)
        self.assertEqual(data.box2_fed_withholding, 12900.00)
        self.assertEqual(data.box12.get("D"), -6000.00)

    def test_parse_w2_box12_dayforce_style(self):
        """Dayforce layout: 'Code DD 6618.00' inline — multi-letter codes."""
        text = """
        Form W-2 2024
        EIN 92-1234567
        1 Wages, tips, other compensation 176008.96
        2 Federal income tax withheld 33321.86
        12a See instructions for box 12 12b
        Code D 10632.00 Code W 1419.84
        12c 12d
        Code DD 6618.00 Code
        14 Other
        """
        data = parse_w2_text(text)
        self.assertEqual(data.box12.get("D"), 10632.00)
        self.assertEqual(data.box12.get("W"), 1419.84)
        self.assertEqual(data.box12.get("DD"), 6618.00)

    def test_parse_w2_box12_webb_style(self):
        """WEBB layout: code letter on its own line after '12x Code' sub-label."""
        text = """
        Form W-2 2024
        EIN 35-1234567
        1 Wages, tips, other comp. 68357.36
        2 Federal income tax withheld 6879.62
        12a Code See inst. for box 12
        D 4686.12
        12b Code
        DD 9664.46
        12c Code
        14 Other
        """
        data = parse_w2_text(text)
        self.assertEqual(data.box12.get("D"), 4686.12)
        self.assertEqual(data.box12.get("DD"), 9664.46)

    def test_parse_w2_employee_name_multiline(self):
        """Employee name is on the line after the 'e Employee's...' label."""
        text = """
        Form W-2 2024
        EIN 92-1234567
        e Employee's first name and initial  Last name  Suff.
        John W  Keel
        1234 Woodrow Ln
        Dallas TX 77512
        1 Wages, tips, other compensation 176008.96
        """
        data = parse_w2_text(text)
        self.assertEqual(data.employee_name, "John W Keel")

    def test_parse_w2_employer_name_multiline(self):
        """Employer name is on the line after 'c Employer's name...' label."""
        text = """
        Form W-2 2024
        c Employer's name, address, and ZIP code
        Cool Company LLP
        1234 Smith Blvd
        Tampa FL 33607
        EIN 92-1234567
        1 Wages, tips, other compensation 176008.96
        """
        data = parse_w2_text(text)
        self.assertEqual(data.employer_name, "Cool Company LLP")

    def test_parse_w2_box13_retirement_plan(self):
        """Box 13 retirement plan checkbox is detected."""
        text = """
        Form W-2 2024
        EIN 92-1234567
        1 Wages, tips, other compensation 176008.96
        13 Statutory Retirement Third-party
        employee plan sick Pay
        X
        14 Other
        """
        data = parse_w2_text(text)
        self.assertTrue(data.box13_retirement_plan)

    def test_parse_w2_box13_retirement_plan_not_checked(self):
        """Box 13 retirement plan is False when not checked."""
        text = """
        Form W-2 2024
        EIN 92-1234567
        1 Wages, tips, other compensation 50000.00
        13 Statutory Retirement Third-party
        employee plan sick Pay
        14 Other
        """
        data = parse_w2_text(text)
        self.assertFalse(data.box13_retirement_plan)

    def test_parse_1098_parentheses_amount(self):
        text = """
        Form 1098 2024
        Lender name: Test Mortgage
        Payer name: Client Name
        Mortgage interest received ($1,200.00)
        """
        data = parse_1098_text(text)
        self.assertEqual(data.mortgage_interest_received, -1200.00)

    def test_parse_brokerage_dollar_amount(self):
        text = """
        2024 Composite Statement
        Broker: Sample Broker
        Ordinary dividends $1,250
        Wash sale ($125.00)
        """
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.div_ordinary, 1250.00)
        self.assertEqual(data.b_summary["wash_sales"], -125.00)


if __name__ == "__main__":
    unittest.main()
