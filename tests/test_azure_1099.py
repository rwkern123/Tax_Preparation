"""
Tests for src/extract/azure_1099.py

All Azure SDK calls are mocked — no real Azure connection required.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build a mock Azure result object
# ---------------------------------------------------------------------------

def _make_field(value):
    f = MagicMock()
    f.value = value
    return f


def _build_azure_result(fields: dict):
    doc = MagicMock()
    doc.fields = fields
    result = MagicMock()
    result.documents = [doc]
    return result


# ---------------------------------------------------------------------------
# Stub out the azure SDK so tests run without the package installed
# ---------------------------------------------------------------------------

def _stub_azure_sdk():
    """Insert minimal stub modules so azure_1099.py imports succeed."""
    azure = types.ModuleType("azure")
    azure_ai = types.ModuleType("azure.ai")
    azure_ai_fr = types.ModuleType("azure.ai.formrecognizer")
    azure_core = types.ModuleType("azure.core")
    azure_core_creds = types.ModuleType("azure.core.credentials")
    azure_core_exc = types.ModuleType("azure.core.exceptions")

    azure_ai_fr.DocumentAnalysisClient = MagicMock
    azure_core_creds.AzureKeyCredential = MagicMock
    azure_core_exc.HttpResponseError = Exception
    azure_core_exc.ServiceRequestError = Exception

    sys.modules.setdefault("azure", azure)
    sys.modules.setdefault("azure.ai", azure_ai)
    sys.modules.setdefault("azure.ai.formrecognizer", azure_ai_fr)
    sys.modules.setdefault("azure.core", azure_core)
    sys.modules.setdefault("azure.core.credentials", azure_core_creds)
    sys.modules.setdefault("azure.core.exceptions", azure_core_exc)


_stub_azure_sdk()

from src.extract.azure_1099 import parse_brokerage_1099_azure  # noqa: E402
import src.extract.azure_1099 as _azure_1099_mod

# Force the availability flag on since stubs are loaded
_azure_1099_mod._AZURE_AVAILABLE = True


FAKE_ENDPOINT = "https://fake.cognitiveservices.azure.com/"
FAKE_KEY = "fake-key-1234"


def _run(fields: dict, tmp_path: Path | None = None):
    """Run parse_brokerage_1099_azure with a mocked Azure client."""
    pdf = tmp_path / "test.pdf" if tmp_path else Path("/nonexistent/test.pdf")
    if tmp_path:
        pdf.write_bytes(b"%PDF-1.4 fake")

    mock_result = _build_azure_result(fields)

    with (
        patch("src.extract.azure_1099.DocumentAnalysisClient") as MockClient,
        patch("src.extract.azure_1099.AzureKeyCredential"),
    ):
        instance = MockClient.return_value
        instance.begin_analyze_document.return_value.result.return_value = mock_result
        return parse_brokerage_1099_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)


class TestParseBrokerage1099Azure(TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmp)

    # -- Happy path ----------------------------------------------------------

    def test_full_fields_returned(self):
        fields = {
            "PayerName": _make_field("Fidelity Investments"),
            "AccountNumber": _make_field("X12345678"),
            "TaxYear": _make_field("2024"),
            "TotalOrdinaryDividends": _make_field(1500.00),
            "QualifiedDividends": _make_field(1200.00),
            "TotalCapitalGainDistributions": _make_field(300.00),
            "ForeignTaxPaid": _make_field(45.00),
            "Section199ADividends": _make_field(100.00),
            "InterestIncome": _make_field(250.00),
            "USTreasuryObligations": _make_field(100.00),
            "GrossProceeds": _make_field(50000.00),
            "CostBasis": _make_field(40000.00),
            "WashSaleDisallowed": _make_field(500.00),
            "ShortTermGainOrLoss": _make_field(3000.00),
            "LongTermGainOrLoss": _make_field(6500.00),
        }
        result = _run(fields, self.tmp_path)

        self.assertIsNotNone(result)
        self.assertEqual(result.broker_name, "Fidelity Investments")
        self.assertEqual(result.account_number, "X12345678")
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.div_ordinary, 1500.00)
        self.assertEqual(result.div_qualified, 1200.00)
        self.assertEqual(result.div_cap_gain_distributions, 300.00)
        self.assertEqual(result.div_foreign_tax_paid, 45.00)
        self.assertEqual(result.div_section_199a, 100.00)
        self.assertEqual(result.int_interest_income, 250.00)
        self.assertEqual(result.int_us_treasury, 100.00)
        self.assertEqual(result.b_summary.get("proceeds"), 50000.00)
        self.assertEqual(result.b_summary.get("cost_basis"), 40000.00)
        self.assertEqual(result.b_summary.get("wash_sales"), 500.00)
        self.assertEqual(result.b_summary.get("short_term_gain_loss"), 3000.00)
        self.assertEqual(result.b_summary.get("long_term_gain_loss"), 6500.00)
        self.assertEqual(result.extraction_source, "azure")

    def test_confidence_calculated_correctly(self):
        # All 10 critical fields populated → min(1.0, 10/10) = 1.0
        fields = {
            "PayerName": _make_field("TD Ameritrade"),
            "AccountNumber": _make_field("999-888"),
            "TotalOrdinaryDividends": _make_field(800.00),
            "QualifiedDividends": _make_field(600.00),
            "InterestIncome": _make_field(50.00),
            "GrossProceeds": _make_field(25000.00),
            "CostBasis": _make_field(20000.00),
            "WashSaleDisallowed": _make_field(0.00),
            "ShortTermGainOrLoss": _make_field(1000.00),
            "LongTermGainOrLoss": _make_field(4000.00),
        }
        result = _run(fields, self.tmp_path)
        self.assertEqual(result.confidence, 1.0)

    def test_partial_fields_lower_confidence(self):
        # Only broker_name + one dividend → 2/10 = 0.20
        fields = {
            "PayerName": _make_field("Schwab"),
            "AccountNumber": _make_field(None),
            "TotalOrdinaryDividends": _make_field(200.00),
            "QualifiedDividends": _make_field(None),
            "InterestIncome": _make_field(None),
            "GrossProceeds": _make_field(None),
            "CostBasis": _make_field(None),
            "WashSaleDisallowed": _make_field(None),
            "ShortTermGainOrLoss": _make_field(None),
            "LongTermGainOrLoss": _make_field(None),
        }
        result = _run(fields, self.tmp_path)
        self.assertIsNotNone(result)
        self.assertLess(result.confidence, 0.5)

    # -- Error handling ------------------------------------------------------

    def test_returns_none_when_no_documents(self):
        pdf = self.tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        empty_result = MagicMock()
        empty_result.documents = []

        with (
            patch("src.extract.azure_1099.DocumentAnalysisClient") as MockClient,
            patch("src.extract.azure_1099.AzureKeyCredential"),
        ):
            instance = MockClient.return_value
            instance.begin_analyze_document.return_value.result.return_value = empty_result
            result = parse_brokerage_1099_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)

        self.assertIsNone(result)

    def test_returns_none_on_http_error(self):
        pdf = self.tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with (
            patch("src.extract.azure_1099.DocumentAnalysisClient") as MockClient,
            patch("src.extract.azure_1099.AzureKeyCredential"),
            patch("src.extract.azure_1099.HttpResponseError", Exception),
        ):
            instance = MockClient.return_value
            instance.begin_analyze_document.side_effect = Exception("HTTP 401")
            result = parse_brokerage_1099_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)

        self.assertIsNone(result)

    def test_returns_none_when_file_not_found(self):
        result = parse_brokerage_1099_azure(Path("/does/not/exist.pdf"), FAKE_ENDPOINT, FAKE_KEY)
        self.assertIsNone(result)
