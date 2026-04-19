"""
Azure Document Intelligence opt-in extraction for Form 1098 (Mortgage Interest Statement).

Uses the prebuilt-tax.us.1098 model. Only called when --enable-azure is set
and local confidence is below threshold. Falls back gracefully if Azure is
unavailable or returns an error.

NOTE: Azure field names are validated against the prebuilt-tax.us.1098 schema.
If a field name does not match, the helper returns None and confidence is reduced
rather than raising an exception — safe to adjust field names after live testing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Confidence threshold below which we attempt Azure extraction
AZURE_CONFIDENCE_THRESHOLD = 0.85

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


def parse_1098_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["Form1098Data"]:  # noqa: F821 — imported at runtime
    """
    Send a Form 1098 PDF to Azure Document Intelligence and return a populated Form1098Data.

    Returns None on any error (network, auth, timeout, parse failure) so the
    caller can fall back to the local regex result without crashing.
    """
    if not _AZURE_AVAILABLE:
        logger.warning(
            "azure-ai-formrecognizer is not installed. "
            "Run: pip install azure-ai-formrecognizer"
        )
        return None

    from src.models import Form1098Data

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
        )

        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.1098", fh)
        result = poller.result()

    except FileNotFoundError:
        logger.warning("azure_1098: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_1098: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_1098: unexpected error: %s", exc)
        return None

    if not result.documents:
        logger.debug("azure_1098: no documents returned for %s", file_path.name)
        return None

    doc = result.documents[0]
    fields = doc.fields or {}

    def _str(name: str) -> Optional[str]:
        f = fields.get(name)
        return f.value if f and f.value is not None else None

    def _float(name: str) -> Optional[float]:
        f = fields.get(name)
        if f is None or f.value is None:
            return None
        try:
            return float(str(f.value).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return None

    def _int(name: str) -> Optional[int]:
        f = fields.get(name)
        if f is None or f.value is None:
            return None
        try:
            return int(str(f.value).strip())
        except (ValueError, TypeError):
            return None

    def _nested_str(parent: str, child: str) -> Optional[str]:
        f = fields.get(parent)
        if f and f.value and hasattr(f.value, "get"):
            sub = f.value.get(child)
            return sub.value if sub and sub.value is not None else None
        return None

    def _nested_float(parent: str, child: str) -> Optional[float]:
        f = fields.get(parent)
        if f and f.value and hasattr(f.value, "get"):
            sub = f.value.get(child)
            if sub and sub.value is not None:
                try:
                    return float(str(sub.value).replace(",", "").replace("$", "").strip())
                except (ValueError, TypeError):
                    pass
        return None

    # Critical fields for confidence scoring
    lender_name = _nested_str("Lender", "Name") or _str("LenderName")
    borrower_name = _nested_str("Borrower", "Name") or _str("BorrowerName")
    mortgage_interest = (
        _nested_float("Box1", "MortgageInterest")
        or _float("Box1")
        or _float("MortgageInterestReceived")
    )
    outstanding_principal = (
        _nested_float("Box2", "OutstandingMortgagePrincipal")
        or _float("Box2")
        or _float("OutstandingMortgagePrincipal")
    )
    mortgage_insurance = (
        _nested_float("Box5", "MortgageInsurancePremiums")
        or _float("Box5")
        or _float("MortgageInsurancePremiums")
    )
    points_paid = (
        _nested_float("Box6", "PointsPaid")
        or _float("Box6")
        or _float("PointsPaid")
    )
    real_estate_taxes = (
        _nested_float("Box10", "Other")
        or _float("Box10")
        or _float("RealEstateTaxes")
    )

    critical = [lender_name, borrower_name, mortgage_interest, outstanding_principal]
    populated_critical = sum(1 for v in critical if v is not None)
    all_fields = [lender_name, borrower_name, mortgage_interest, outstanding_principal,
                  mortgage_insurance, points_paid, real_estate_taxes]
    populated_all = sum(1 for v in all_fields if v is not None)
    azure_confidence = round(min(1.0, populated_critical / 4 * 0.7 + populated_all / 7 * 0.3), 2)

    data = Form1098Data(
        lender_name=lender_name,
        payer_name=borrower_name,
        borrower_names=[borrower_name] if borrower_name else [],
        year=_int("TaxYear"),
        mortgage_interest_received=mortgage_interest,
        mortgage_principal_outstanding=outstanding_principal,
        mortgage_insurance_premiums=mortgage_insurance,
        points_paid=points_paid,
        real_estate_taxes=real_estate_taxes,
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_1098: extracted %s with confidence %.2f for %s",
        data.lender_name or "unknown lender",
        azure_confidence,
        file_path.name,
    )
    return data
