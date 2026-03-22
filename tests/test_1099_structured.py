"""Tests for the CSV and XML 1099 parsers using example files."""
from __future__ import annotations

import unittest
from pathlib import Path

EXAMPLES = Path(__file__).parent.parent / "examples" / "forms" / "1099"


class TestBrokerage1099CSV(unittest.TestCase):
    def _parse(self, filename: str):
        from src.extract.brokerage_1099_csv import parse_brokerage_1099_csv
        path = EXAMPLES / filename
        content = path.read_text(encoding="utf-8", errors="replace")
        return parse_brokerage_1099_csv(content, source_file=filename)

    def test_341_2025_div_int(self):
        data, trades = self._parse("XXXX-X341 (1).CSV")
        self.assertEqual(data.year, 2025)
        self.assertEqual(data.account_number, "XXXX-X341")
        self.assertAlmostEqual(data.div_ordinary, 1008.05)
        self.assertAlmostEqual(data.div_qualified, 122.60)
        self.assertAlmostEqual(data.div_section_199a, 3.20)
        self.assertAlmostEqual(data.int_interest_income, 2.69)
        self.assertIsNone(data.div_foreign_tax_paid)

    def test_341_2025_trades(self):
        data, trades = self._parse("XXXX-X341 (1).CSV")
        self.assertGreater(len(trades), 0)
        # First trade: 30 INTELLIA THERAPEUTICS short-term covered
        first = trades[0]
        self.assertIn("INTELLIA", first.description)
        self.assertEqual(first.holding_period, "short")
        self.assertEqual(first.basis_reported_to_irs, "covered")
        self.assertAlmostEqual(first.proceeds_gross, 359.22)
        self.assertAlmostEqual(first.cost_basis, 357.90)
        self.assertEqual(first.form_8949_box, "A")

    def test_341_wash_sale(self):
        data, trades = self._parse("XXXX-X341 (1).CSV")
        # STRATEGY INC trade has a wash sale amount of $1024.17
        strategy_trades = [t for t in trades if "STRATEGY" in t.description]
        self.assertTrue(any(t.wash_sale_amount and t.wash_sale_amount > 0 for t in strategy_trades))

    def test_898_2021_div_only(self):
        data, trades = self._parse("XXXX-X898.CSV")
        self.assertEqual(data.year, 2021)
        self.assertAlmostEqual(data.div_ordinary, 19.71)
        # 2021 file has no INT data - interest income will be None
        self.assertIsNone(data.int_interest_income)

    def test_781_2025_foreign_tax(self):
        data, trades = self._parse("XXXX-X781.CSV")
        self.assertAlmostEqual(data.div_ordinary, 2423.44)
        self.assertAlmostEqual(data.div_foreign_tax_paid, 1.33)

    def test_confidence_nonzero(self):
        data, _ = self._parse("XXXX-X341 (1).CSV")
        self.assertGreater(data.confidence, 0.0)

    def test_extraction_source(self):
        data, _ = self._parse("XXXX-X341 (1).CSV")
        self.assertEqual(data.extraction_source, "csv")


class TestBrokerage1099XML(unittest.TestCase):
    def _parse(self, filename: str):
        from src.extract.brokerage_1099_xml import parse_brokerage_1099_xml
        path = EXAMPLES / filename
        content = path.read_text(encoding="utf-8", errors="replace")
        return parse_brokerage_1099_xml(content, source_file=filename)

    def test_341_2025_div_int(self):
        data, trades = self._parse("XXXX-X341.XML")
        self.assertEqual(data.year, 2025)
        self.assertAlmostEqual(data.div_ordinary, 1008.05)
        self.assertAlmostEqual(data.div_qualified, 122.60)
        self.assertAlmostEqual(data.div_section_199a, 3.20)
        self.assertAlmostEqual(data.int_interest_income, 2.69)

    def test_341_2025_trades(self):
        data, trades = self._parse("XXXX-X341.XML")
        self.assertGreater(len(trades), 0)
        first = trades[0]
        self.assertIn("INTELLIA", first.description)
        self.assertEqual(first.holding_period, "short")
        self.assertEqual(first.basis_reported_to_irs, "covered")
        self.assertAlmostEqual(first.proceeds_gross, 359.22)
        self.assertAlmostEqual(first.cost_basis, 357.90)
        self.assertEqual(first.form_8949_box, "A")

    def test_341_noncovered(self):
        data, trades = self._parse("XXXX-X341.XML")
        noncovered = [t for t in trades if t.basis_reported_to_irs == "noncovered"]
        self.assertGreater(len(noncovered), 0)

    def test_341_wash_sale(self):
        data, trades = self._parse("XXXX-X341.XML")
        wash_trades = [t for t in trades if t.wash_sale_amount and t.wash_sale_amount > 0]
        self.assertGreater(len(wash_trades), 0)
        self.assertAlmostEqual(wash_trades[0].wash_sale_amount, 1024.17)

    def test_898_2021_div_only(self):
        data, trades = self._parse("XXXX-X898.XML")
        self.assertEqual(data.year, 2021)
        self.assertAlmostEqual(data.div_ordinary, 19.71)
        self.assertEqual(len(trades), 0)

    def test_781_2025_foreign_tax(self):
        data, trades = self._parse("XXXX-X781.XML")
        self.assertAlmostEqual(data.div_ordinary, 2423.44)
        self.assertAlmostEqual(data.div_foreign_tax_paid, 1.33)

    def test_broker_name(self):
        data, _ = self._parse("XXXX-X341.XML")
        self.assertIn("Schwab", data.broker_name)

    def test_extraction_source(self):
        data, _ = self._parse("XXXX-X341.XML")
        self.assertEqual(data.extraction_source, "xml")

    def test_trade_count_matches_csv(self):
        """XML and CSV for the same account/year should produce comparable trade counts."""
        from src.extract.brokerage_1099_csv import parse_brokerage_1099_csv
        csv_path = EXAMPLES / "XXXX-X341 (1).CSV"
        _, xml_trades = self._parse("XXXX-X341.XML")
        _, csv_trades = parse_brokerage_1099_csv(
            csv_path.read_text(encoding="utf-8", errors="replace"), source_file="XXXX-X341 (1).CSV"
        )
        # Both sources should produce a similar number of trades (within 5%)
        self.assertGreater(len(xml_trades), 0)
        self.assertGreater(len(csv_trades), 0)
        ratio = len(xml_trades) / len(csv_trades)
        self.assertAlmostEqual(ratio, 1.0, delta=0.05)


class TestClassifyStructured(unittest.TestCase):
    def test_csv_classified_as_brokerage(self):
        from src.classify import classify_document_structured
        path = EXAMPLES / "XXXX-X341 (1).CSV"
        result = classify_document_structured(path)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "brokerage_1099")
        self.assertEqual(result[1], 1.0)

    def test_xml_classified_as_brokerage(self):
        from src.classify import classify_document_structured
        path = EXAMPLES / "XXXX-X341.XML"
        result = classify_document_structured(path)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "brokerage_1099")
        self.assertEqual(result[1], 1.0)

    def test_pdf_returns_none(self):
        from src.classify import classify_document_structured
        path = EXAMPLES / "1099 Composite and Year-End Summary - 2024_2025-02-07_341.PDF"
        result = classify_document_structured(path)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
