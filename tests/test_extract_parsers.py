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
