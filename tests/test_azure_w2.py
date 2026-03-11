"""
Tests for src/extract/azure_w2.py

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


def _make_nested(mapping: dict):
    """Return a field whose .value behaves like a dict with .get()."""
    container = MagicMock()
    inner = {k: _make_field(v) for k, v in mapping.items()}
    container.value = MagicMock()
    container.value.get = lambda k, default=None: inner.get(k, _make_field(None))
    return container


def _make_state_list(state: str, wages: float, tax: float):
    """Return a field whose .value is a list of state-tax entries."""
    entry = MagicMock()
    inner = {
        "State": _make_field(state),
        "StateWages": _make_field(wages),
        "StateIncomeTax": _make_field(tax),
    }
    entry.value = MagicMock()
    entry.value.get = lambda k, default=None: inner.get(k, _make_field(None))
    container = MagicMock()
    container.value = [entry]
    return container


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
    """Insert minimal stub modules so azure_w2.py imports succeed."""
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

from src.extract.azure_w2 import parse_w2_azure  # noqa: E402
import src.extract.azure_w2 as _azure_w2_mod

# Force the availability flag on since stubs are loaded
_azure_w2_mod._AZURE_AVAILABLE = True


FAKE_ENDPOINT = "https://fake.cognitiveservices.azure.com/"
FAKE_KEY = "fake-key-1234"
FAKE_PDF = Path(__file__).parent / "__fixtures__" / "fake_w2.pdf"


def _run(fields: dict, tmp_path: Path | None = None):
    """Run parse_w2_azure with a mocked Azure client against the given fields dict."""
    pdf = tmp_path / "test.pdf" if tmp_path else Path("/nonexistent/test.pdf")
    if tmp_path:
        pdf.write_bytes(b"%PDF-1.4 fake")

    mock_result = _build_azure_result(fields)

    with (
        patch("src.extract.azure_w2.DocumentAnalysisClient") as MockClient,
        patch("src.extract.azure_w2.AzureKeyCredential"),
    ):
        instance = MockClient.return_value
        instance.begin_analyze_document.return_value.result.return_value = mock_result
        return parse_w2_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)


class TestParseW2Azure(TestCase):

    def setUp(self):
        import tempfile, os
        self._tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self._tmp)

    # -- Happy path ----------------------------------------------------------

    def test_full_fields_returned(self):
        fields = {
            "Employer": _make_nested({"Name": "Acme Corp", "IdNumber": "12-3456789", "Address": "123 Main St"}),
            "Employee": _make_nested({"Name": "John Doe", "Address": "456 Elm St"}),
            "WagesTipsAndOtherCompensation": _make_field(75000.0),
            "FederalIncomeTaxWithheld": _make_field(12000.0),
            "SocialSecurityWages": _make_field(75000.0),
            "SocialSecurityTaxWithheld": _make_field(4650.0),
            "MedicareWagesAndTips": _make_field(75000.0),
            "MedicareTaxWithheld": _make_field(1087.5),
            "StateAndLocalTaxesGroup": _make_state_list("CA", 75000.0, 5000.0),
        }
        result = _run(fields, self.tmp_path)

        self.assertIsNotNone(result)
        self.assertEqual(result.employer_name, "Acme Corp")
        self.assertEqual(result.employer_ein, "12-3456789")
        self.assertEqual(result.employee_name, "John Doe")
        self.assertEqual(result.box1_wages, 75000.0)
        self.assertEqual(result.box2_fed_withholding, 12000.0)
        self.assertEqual(result.box3_ss_wages, 75000.0)
        self.assertEqual(result.box4_ss_tax, 4650.0)
        self.assertEqual(result.box5_medicare_wages, 75000.0)
        self.assertEqual(result.box6_medicare_tax, 1087.5)
        self.assertEqual(result.box16_state_wages, 75000.0)
        self.assertEqual(result.box17_state_tax, 5000.0)
        self.assertEqual(result.extraction_source, "azure")

    def test_confidence_calculated_correctly(self):
        # All 9 critical fields populated + box1 bonus → min(1.0, 9/9 + 0.1) = 1.0
        fields = {
            "Employer": _make_nested({"Name": "Corp", "IdNumber": "99-9999999"}),
            "Employee": _make_nested({"Name": "Jane Smith"}),
            "WagesTipsAndOtherCompensation": _make_field(50000.0),
            "FederalIncomeTaxWithheld": _make_field(8000.0),
            "SocialSecurityWages": _make_field(50000.0),
            "SocialSecurityTaxWithheld": _make_field(3100.0),
            "MedicareWagesAndTips": _make_field(50000.0),
            "MedicareTaxWithheld": _make_field(725.0),
            "StateAndLocalTaxesGroup": _make_state_list("TX", 50000.0, 0.0),
        }
        result = _run(fields, self.tmp_path)
        self.assertEqual(result.confidence, 1.0)

    def test_partial_fields_lower_confidence(self):
        # Only employer name + box1 → 2/9 + 0.1 bonus = ~0.32
        fields = {
            "Employer": _make_nested({"Name": "PartialCorp", "IdNumber": None}),
            "Employee": _make_nested({"Name": None}),
            "WagesTipsAndOtherCompensation": _make_field(30000.0),
            "FederalIncomeTaxWithheld": _make_field(None),
            "SocialSecurityWages": _make_field(None),
            "SocialSecurityTaxWithheld": _make_field(None),
            "MedicareWagesAndTips": _make_field(None),
            "MedicareTaxWithheld": _make_field(None),
            "StateAndLocalTaxesGroup": _make_state_list(None, None, None),
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
            patch("src.extract.azure_w2.DocumentAnalysisClient") as MockClient,
            patch("src.extract.azure_w2.AzureKeyCredential"),
        ):
            instance = MockClient.return_value
            instance.begin_analyze_document.return_value.result.return_value = empty_result
            result = parse_w2_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)

        self.assertIsNone(result)

    def test_returns_none_on_http_error(self):
        pdf = self.tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with (
            patch("src.extract.azure_w2.DocumentAnalysisClient") as MockClient,
            patch("src.extract.azure_w2.AzureKeyCredential"),
            patch("src.extract.azure_w2.HttpResponseError", Exception),
        ):
            instance = MockClient.return_value
            instance.begin_analyze_document.side_effect = Exception("HTTP 401")
            result = parse_w2_azure(pdf, FAKE_ENDPOINT, FAKE_KEY)

        self.assertIsNone(result)

    def test_returns_none_when_file_not_found(self):
        result = parse_w2_azure(Path("/does/not/exist.pdf"), FAKE_ENDPOINT, FAKE_KEY)
        self.assertIsNone(result)
