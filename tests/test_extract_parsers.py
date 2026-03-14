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

    def test_parse_brokerage_account_number(self):
        text = "2024 Schwab Composite 1099\nAccount Number: 3652-3341\nOrdinary dividends 100.00"
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.account_number, "3652-3341")

    def test_parse_brokerage_section_199a(self):
        text = "2024 Schwab Composite 1099\n5 Section 199A Dividends $ 1.89\nOrdinary dividends 50.00"
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.div_section_199a, 1.89)

    def test_parse_brokerage_section_1256(self):
        text = (
            "2024 Schwab Composite 1099\n"
            "Total of Options Subject to Section 1256 Reporting $ 512.85\n"
        )
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.section_1256_net_gain_loss, 512.85)

    def test_parse_brokerage_short_term_covered(self):
        text = (
            "2024 Schwab Composite 1099\n"
            "Basis is Reported to the IRS\n"
            "Total Short-Term      (1,234.56)\n"
            "Total Long-Term       500.00\n"
        )
        data = parse_brokerage_1099_text(text)
        self.assertEqual(data.b_short_term_covered, -1234.56)
        self.assertEqual(data.b_long_term_covered, 500.00)
        self.assertIsNone(data.b_short_term_noncovered)
        self.assertIsNone(data.b_long_term_noncovered)


    def test_parse_w2_idms_style(self):
        """IDMS payroll: 'Depress F1 for codes' label, '$' amounts, multi-line employer name."""
        text = (
            "W-2 - IDMS\n"
            "a Employee's SSN\n"
            "102110029\n"
            "b Employer identification number (EIN)\n"
            "99-9999999 (941)\n"
            "c Employer's name, address, and ZIP code\n"
            "INTEGRATED DATA MANAGEMENT SYSTEMS\n"
            "ACCOUNT ABILITY COMPLIANCE SOFTWARE\n"
            "555 BROADHOLLOW ROAD SUITE 273\n"
            "MELVILLE NY 11747-5001\n"
            "1 Wages, tips, other comp\n"
            "$385,000.00\n"
            "2 Federal income tax withheld\n"
            "$102,255.00\n"
            "3 Social security wages\n"
            "$138,600.00\n"
            "4 Social security tax withheld\n"
            "$10,918.20\n"
            "5 Medicare wages and tips\n"
            "$402,575.00\n"
            "6 Medicare tax withheld\n"
            "$7,660.52\n"
            "12a - Depress F1 for codes\n"
            "S $17,575.00\n"
            "12b - Depress F1 for codes\n"
            "FF $52,500.00\n"
            "12c - Depress F1 for codes\n"
            "DD $9,340.00\n"
            "12d - Depress F1 for codes\n"
            "J $7,692.00\n"
            "e Employee's first name MI Last name\n"
            "JOHN M DOE\n"
            "33 EAST 17 STREET STE 201\n"
            "NEW YORK NY 10003\n"
            "2025 - Form W-2 Wage and Tax Statement\n"
        )
        data = parse_w2_text(text)
        self.assertEqual(data.employer_ein, "99-9999999")
        self.assertEqual(data.employer_name, "INTEGRATED DATA MANAGEMENT SYSTEMS")
        self.assertEqual(data.employer_city, "MELVILLE")
        self.assertEqual(data.employer_state, "NY")
        self.assertEqual(data.employer_zip, "11747-5001")
        self.assertEqual(data.employee_name, "JOHN M DOE")
        self.assertEqual(data.box1_wages, 385000.00)
        self.assertEqual(data.box2_fed_withholding, 102255.00)
        self.assertEqual(data.box12.get("S"), 17575.00)
        self.assertEqual(data.box12.get("FF"), 52500.00)
        self.assertEqual(data.box12.get("DD"), 9340.00)
        self.assertEqual(data.box12.get("J"), 7692.00)

    def test_parse_w2_adp_style(self):
        """ADP W-2: 'e/f Employee's name' combined label and box 12 on next line."""
        text = (
            "W-2 Wage and Tax 20XX\n"
            "c Employer's name, address, and ZIP code\n"
            "SAMPLE COMPANY INC\n"
            "123 MAIN ST\n"
            "ANYWHERE CA 123456\n"
            "b Employer's FED ID number\n"
            "12-3456789\n"
            "e/f Employee's name, address, and ZIP code\n"
            "JOHN SMITH\n"
            "1234 S MAPLE ST\n"
            "ANYWHERE CA 123456\n"
            "1 Wages, tips, other comp.\n"
            "23500.00\n"
            "2 Federal income tax withheld\n"
            "1500.00\n"
            "3 Social security wages\n"
            "23500.00\n"
            "4 Social security tax withheld\n"
            "1457.00\n"
            "5 Medicare wages and tips\n"
            "23500.00\n"
            "6 Medicare tax withheld\n"
            "340.75\n"
            "12a See instructions for box 12\n"
            "W 500.00\n"
            "16 State wages, tips, etc.\n"
            "23500.00\n"
            "17 State income tax\n"
            "800.00\n"
        )
        data = parse_w2_text(text)
        self.assertEqual(data.employer_ein, "12-3456789")
        self.assertEqual(data.employee_name, "JOHN SMITH")
        self.assertEqual(data.box1_wages, 23500.00)
        self.assertEqual(data.box2_fed_withholding, 1500.00)
        self.assertEqual(data.box12.get("W"), 500.00)
        self.assertEqual(data.box16_state_wages, 23500.00)
        self.assertEqual(data.box17_state_tax, 800.00)

    def test_parse_w2_irs_official_style(self):
        """IRS official Copy A/B: split first-name/last-name columns, 'f' address label."""
        text = (
            "b Employer identification number (EIN)\n"
            "12-1234567\n"
            "c Employer's name, address, and ZIP code\n"
            "Company ABC\n"
            "444 Example Road\n"
            "Columbus OH 43218\n"
            "1 Wages, tips, other compensation\n"
            "50000.00\n"
            "2 Federal income tax withheld\n"
            "4300.00\n"
            "3 Social security wages\n"
            "50000.00\n"
            "4 Social security tax withheld\n"
            "3100.00\n"
            "5 Medicare wages and tips\n"
            "50000.00\n"
            "6 Medicare tax withheld\n"
            "725.00\n"
            "e Employee's first name and initial  Last name  Suff.\n"
            "Abby L  Smith\n"
            "f Employee's address and ZIP code\n"
            "123 Sample Road\n"
            "Columbus OH 43218\n"
            "15 State  16 State wages, tips, etc.  17 State income tax\n"
            "OH  12-3456789  50000.00  1000.63\n"
            "Form W-2 Wage and Tax Statement 2025\n"
        )
        data = parse_w2_text(text)
        self.assertEqual(data.year, 2025)
        self.assertEqual(data.employer_ein, "12-1234567")
        self.assertEqual(data.employer_name, "Company ABC")
        self.assertEqual(data.employer_city, "Columbus")
        self.assertEqual(data.employer_state, "OH")
        self.assertEqual(data.employee_name, "Abby L Smith")
        self.assertEqual(data.box1_wages, 50000.00)
        self.assertEqual(data.box2_fed_withholding, 4300.00)
        self.assertEqual(data.box16_state_wages, 50000.00)

    def test_parse_w2_irs_split_name_columns(self):
        """IRS form where pdfplumber separates first-name and last-name onto individual lines."""
        text = (
            "Form W-2 Wage and Tax Statement 2023\n"
            "b Employer identification number (EIN)\n"
            "12-3456789\n"
            "c Employer's name, address, and ZIP code\n"
            "New Technology Company\n"
            "100 Somewhere Rd Suite 123\n"
            "Los Angeles CA 90000\n"
            "1 Wages, tips, other compensation  2736.09\n"
            "e Employee's first name and initial\n"
            "Last name\n"
            "John J\n"
            "Hall\n"
            "Flower Lane\n"
            "Los Angeles CA 94001\n"
        )
        data = parse_w2_text(text)
        # Should skip the "Last name" sub-header and capture the actual name
        self.assertNotEqual(data.employee_name, "Last name")
        self.assertIsNotNone(data.employee_name)


if __name__ == "__main__":
    unittest.main()
