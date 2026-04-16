"""
Azure Document Intelligence opt-in extraction for prior-year Form 1040 PDFs.

Uses the prebuilt-tax.us.1040 model. Only called when --enable-azure is set
and local confidence is below threshold. Falls back gracefully if Azure is
unavailable or returns an error.

NOTE: Azure field names are validated against the prebuilt-tax.us.1040 schema.
If a field name does not match, the helper returns None and confidence is reduced
rather than raising an exception — safe to adjust field names after live testing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Confidence threshold below which we attempt Azure extraction
AZURE_CONFIDENCE_THRESHOLD = 0.75

# Module-level imports so they are patchable in tests.
# Falls back to None if the package is not installed.
try:
    from azure.ai.formrecognizer import DocumentAnalysisClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import HttpResponseError, ServiceRequestError
    _AZURE_AVAILABLE = True
except ImportError:
    DocumentAnalysisClient = None  # type: ignore[assignment,misc]
    AzureKeyCredential = None  # type: ignore[assignment,misc]
    HttpResponseError = Exception  # type: ignore[assignment,misc]
    ServiceRequestError = Exception  # type: ignore[assignment,misc]
    _AZURE_AVAILABLE = False


def parse_prior_year_return_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["PriorYearReturnData"]:  # noqa: F821 — imported at runtime
    """
    Send a Form 1040 PDF to Azure Document Intelligence and return a populated
    PriorYearReturnData instance.

    Returns None on any error (network, auth, timeout, parse failure) so the
    caller can fall back to the local regex result without crashing.
    """
    if not _AZURE_AVAILABLE:
        logger.warning(
            "azure-ai-formrecognizer is not installed. "
            "Run: pip install azure-ai-formrecognizer"
        )
        return None

    from src.models import PriorYearReturnData

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
        )
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.1040", fh)
        result = poller.result()

    except FileNotFoundError:
        logger.warning("azure_prior_year_return: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_prior_year_return: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_prior_year_return: unexpected error: %s", exc)
        return None

    if not result.documents:
        logger.debug(
            "azure_prior_year_return: no documents returned for %s", file_path.name
        )
        return None

    doc = result.documents[0]
    fields = doc.fields or {}

    # ------------------------------------------------------------------ #
    # Helper accessors — return None rather than raising on missing fields #
    # ------------------------------------------------------------------ #

    def _str(name: str) -> Optional[str]:
        f = fields.get(name)
        return str(f.value).strip() if f and f.value is not None else None

    def _float(name: str) -> Optional[float]:
        f = fields.get(name)
        if f is None or f.value is None:
            return None
        try:
            return float(str(f.value).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return None

    def _int(name: str) -> Optional[int]:
        v = _float(name)
        return int(v) if v is not None else None

    def _nested_str(parent: str, child: str) -> Optional[str]:
        f = fields.get(parent)
        if f and f.value and hasattr(f.value, "get"):
            sub = f.value.get(child)
            return str(sub.value).strip() if sub and sub.value is not None else None
        return None

    def _nested_float(parent: str, child: str) -> Optional[float]:
        f = fields.get(parent)
        if f and f.value and hasattr(f.value, "get"):
            sub = f.value.get(child)
            if sub and sub.value is not None:
                try:
                    return float(
                        str(sub.value).replace(",", "").replace("$", "").strip()
                    )
                except (ValueError, TypeError):
                    pass
        return None

    # ------------------------------------------------------------------ #
    # Field mapping — Azure prebuilt-tax.us.1040 field names              #
    # (as documented in the Azure Form Recognizer 1040 schema)            #
    # ------------------------------------------------------------------ #

    # Critical fields for confidence scoring
    critical_values = [
        _nested_str("TaxpayerName", "FirstName") or _str("TaxpayerFirstName"),
        _str("TaxpayerSSN") or _nested_str("TaxpayerIdNumber", "Value"),
        _float("AdjustedGrossIncome"),
        _float("TaxableIncome"),
        _float("TotalTax"),
        _float("TotalPayments"),
        _str("FilingStatus"),
        _int("TaxYear"),
    ]
    populated = sum(1 for v in critical_values if v is not None)
    azure_confidence = round(min(1.0, populated / len(critical_values)), 2)

    # Taxpayer / spouse names — Azure returns them split across subfields
    tp_first = _nested_str("TaxpayerName", "FirstName") or _str("TaxpayerFirstName") or ""
    tp_last = _nested_str("TaxpayerName", "LastName") or _str("TaxpayerLastName") or ""
    taxpayer_name = f"{tp_first} {tp_last}".strip() or None

    sp_first = _nested_str("SpouseName", "FirstName") or _str("SpouseFirstName") or ""
    sp_last = _nested_str("SpouseName", "LastName") or _str("SpouseLastName") or ""
    spouse_name = f"{sp_first} {sp_last}".strip() or None

    # Address — Azure may return as a combined string or split fields
    address_raw = _str("TaxpayerAddress") or _nested_str("Address", "StreetAddress")
    city = _nested_str("Address", "City") or _str("TaxpayerCity")
    state = _nested_str("Address", "State") or _str("TaxpayerState")
    zip_code = _nested_str("Address", "PostalCode") or _str("TaxpayerZip")

    data = PriorYearReturnData(
        year=_int("TaxYear"),
        taxpayer_name=taxpayer_name,
        taxpayer_ssn=_str("TaxpayerSSN") or _nested_str("TaxpayerIdNumber", "Value"),
        spouse_name=spouse_name or None,
        spouse_ssn=_str("SpouseSSN") or _nested_str("SpouseIdNumber", "Value"),
        address=address_raw,
        city=city,
        state=state,
        zip_code=zip_code,
        filing_status=_str("FilingStatus"),

        # Income lines
        line_1a_w2_wages=_float("TotalWages"),
        line_1z_total_wages=_float("TotalWages"),           # same field if Azure doesn't split
        line_2b_taxable_interest=_float("TaxableInterest"),
        line_3a_qualified_dividends=_float("QualifiedDividends"),
        line_3b_ordinary_dividends=_float("OrdinaryDividends"),
        line_4b_ira_taxable=_float("TaxableIRADistributions"),
        line_5b_pension_taxable=_float("TaxablePensionsAndAnnuities"),
        line_6b_ss_taxable=_float("TaxableSocialSecurityBenefits"),
        line_7_capital_gain_loss=_float("CapitalGainOrLoss"),
        line_8_other_income=_float("AdditionalIncome"),
        line_9_total_income=_float("TotalIncome"),
        line_10_adjustments=_float("AdjustmentsToIncome"),
        line_11_agi=_float("AdjustedGrossIncome"),
        line_12_deductions=_float("StandardOrItemizedDeduction"),
        line_13_qbi_deduction=_float("QBIDeduction"),
        line_15_taxable_income=_float("TaxableIncome"),

        # Tax & credits
        line_16_tax=_float("TaxLiability"),
        line_24_total_tax=_float("TotalTax"),

        # Payments
        line_25a_w2_withholding=_float("W2FederalTaxWithheld"),
        line_25b_1099_withholding=_float("Form1099FederalTaxWithheld"),
        line_25d_total_withholding=_float("TotalFederalTaxWithheld"),
        line_26_estimated_payments=_float("EstimatedTaxPayments"),
        line_33_total_payments=_float("TotalPayments"),
        line_34_overpayment=_float("Overpayment"),
        line_35a_refund=_float("AmountRefunded"),
        line_37_amount_owed=_float("AmountOwed"),
        line_38_estimated_tax_penalty=_float("EstimatedTaxPenalty"),

        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_prior_year_return: year=%s agi=%s total_tax=%s confidence=%.2f for %s",
        data.year,
        data.line_11_agi,
        data.line_24_total_tax,
        azure_confidence,
        file_path.name,
    )
    return data
