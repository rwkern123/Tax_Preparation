import unittest

from src.extract.brokerage_1099 import parse_brokerage_1099_text
from src.extract.form_1098 import parse_1098_text
from src.extract.w2 import parse_w2_text


class TestParsers(unittest.TestCase):
    def test_parse_w2(self):
        text = """
        Form W-2 2024
        c Employer's name, address, and ZIP code
        ABC Corp
        200 West Street
        New York, NY 10282
        EIN 12-3456789
        e Employee's first name
        John Smith
        456 Elm Ave
        Albany, NY 12207
        Box 1 Wages 85,200.00
        Box 2 Federal income tax withheld 12,900.00
        Box 12 D 6,000.00
        Box 16 State wages 85,200.00
        Box 17 State income tax 4,100.00
        """
        data = parse_w2_text(text)
        self.assertEqual(data.employer_ein, "12-3456789")
        self.assertEqual(data.box1_wages, 85200.00)
        self.assertIn("D", data.box12)
        self.assertEqual(data.employer_state, "NY")
        self.assertEqual(data.employer_city, "New York")
        self.assertEqual(data.employer_zip, "10282")
        self.assertEqual(data.employer_address, "200 West Street")
        self.assertEqual(data.employee_state, "NY")
        self.assertEqual(data.employee_city, "Albany")
        self.assertEqual(data.employee_zip, "12207")

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

    def test_parse_w2_dayforce_real_pdf(self):
        """Dayforce W2: actual pdfplumber text — no box labels, W-2 Wages summary line,
        garbled first copy, clean employee name in final copy."""
        text = (
            "4/11/25, 10:51 PM Earnings - Dayforce\n"
            "Federal Box 1 Soc. Sec. Box 3 & 7 Medicare Box 5\n"
            "To the right is information which shows your total wages by"
            " Gross Wages 187199.96 187199.96 187199.96\n"
            "W-2 box and the amount of any deferred compensation and/or"
            " Txbl Benefits 1475.00 1475.00 1475.00\n"
            "W-2 Wages 176008.96 168600.00 186640.96\n"
            "XXX-XX-1234 92-1234567 17123456\n"
            "176008.96 33321.86\n"
            "Cool Company LLP\n"
            "1234 Smith Blvd\n"
            "Tampa FL 33607 168600.00 10453.20\n"
            "186640.96 2706.29\n"
            "1\nJo\n2\nh\n3\nn\n4\nW\nWoodrow Ln\nKeel\nDallasTX 77512\nUSA\n"
            "D 10632.00\n"
            "W 1419.84\n"
            "X\n"
            "DD 6618.00\n"
            "2024\n"
            "Tampa FL 33607 168600.00 10453.20\n"
            "186640.96 2706.29\n"
            "Ryan W Keel\n"
            "1234Woodrow Ln\n"
            "Dallas TX 77512\n"
            "USA\n"
            "D 10632.00\n"
            "W 1419.84\n"
            "X\n"
            "DD 6618.00\n"
            "2024\n"
        )
        data = parse_w2_text(text)
        self.assertEqual(data.year, 2024)
        self.assertEqual(data.employer_ein, "92-1234567")
        self.assertEqual(data.employer_name, "Cool Company LLP")
        self.assertEqual(data.employee_name, "Ryan W Keel")
        self.assertEqual(data.box1_wages, 176008.96)
        self.assertEqual(data.box2_fed_withholding, 33321.86)
        self.assertEqual(data.box3_ss_wages, 168600.00)
        self.assertEqual(data.box4_ss_tax, 10453.20)
        self.assertEqual(data.box5_medicare_wages, 186640.96)
        self.assertEqual(data.box6_medicare_tax, 2706.29)
        self.assertEqual(data.box12.get("D"), 10632.00)
        self.assertEqual(data.box12.get("W"), 1419.84)
        self.assertEqual(data.box12.get("DD"), 6618.00)
        self.assertTrue(data.box13_retirement_plan)

    def test_parse_w2_webb_real_pdf(self):
        """WEBB W2: actual pdfplumber text — no labels, doubled side-by-side copies,
        partial EIN, no year in extracted text."""
        text = (
            "68357.36 6879.62 68357.36 6879.62\n"
            "73043.48 4528.70 73043.48 4528.70\n"
            "35- 35-\n"
            "73043.48 1059.13 73043.48 1059.13\n"
            "The Companies, Inc. The Companies, Inc.\n"
            "An Affiliate of Inc. An Affiliate Inc.\n"
            "220 Avenue 220 Avenue\n"
            "Indianapolis, IN 46204 Indianapolis, IN 46204\n"
            "BRITTANY T WEBB BRITTANY T WEBB\n"
            "6311 Woodbrook Ln 6311 Woodbrook Ln\n"
            "Houston, TX 77008 Houston, TX 77008\n"
            "D 4686.12 D 4686.12\n"
            "DD 9664.46 DD 9664.46\n"
            "X X\n"
        )
        data = parse_w2_text(text)
        # No year in pdfplumber output for this form
        self.assertIsNone(data.year)
        # EIN is redacted (only "35-" visible); parser correctly finds nothing
        self.assertIsNone(data.employer_ein)
        self.assertEqual(data.employer_name, "The Companies, Inc.")
        self.assertEqual(data.employee_name, "BRITTANY T WEBB")
        self.assertEqual(data.box1_wages, 68357.36)
        self.assertEqual(data.box2_fed_withholding, 6879.62)
        self.assertEqual(data.box3_ss_wages, 73043.48)
        self.assertEqual(data.box4_ss_tax, 4528.70)
        self.assertEqual(data.box5_medicare_wages, 73043.48)
        self.assertEqual(data.box6_medicare_tax, 1059.13)
        self.assertEqual(data.box12.get("D"), 4686.12)
        self.assertEqual(data.box12.get("DD"), 9664.46)
        self.assertTrue(data.box13_retirement_plan)

    def test_parse_w2_employee_name_allcaps(self):
        """All-caps employee name (e.g. WEBB PDF) is extracted by positional pattern."""
        text = (
            "034-80-5887 68357.36 6879.62\n"
            "35-1835818\n"
            "73043.48 4528.70\n"
            "73043.48 1059.13\n"
            "The Elevance Health Companies, Inc.\n"
            "An Affiliate of Elevance Health, Inc.\n"
            "220 Virginia Avenue\n"
            "Indianapolis, IN 46204\n"
            "BRITTANY T WEBB\n"
            "6311 Woodbrook Ln\n"
            "Houston, TX 77008\n"
            "D 4686.12\n"
            "DD 9664.46\n"
            "X\n"
        )
        data = parse_w2_text(text)
        self.assertEqual(data.employee_name, "BRITTANY T WEBB")

    def test_parse_w2_fallback_year(self):
        """fallback_year is used when no year can be extracted from text."""
        text = (
            "35-1835818\n"
            "68357.36 6879.62\n"
            "73043.48 4528.70\n"
            "73043.48 1059.13\n"
            "The Elevance Health Companies, Inc.\n"
        )
        data = parse_w2_text(text, fallback_year=2024)
        self.assertEqual(data.year, 2024)

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
