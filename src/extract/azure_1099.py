"""
Azure Document Intelligence opt-in extraction for brokerage composite 1099 documents.

Uses the prebuilt-tax.us.1099b model. Only called when --enable-azure is set
and local confidence is below threshold. Falls back gracefully if Azure is
unavailable or returns an error.

NOTE: Azure field names are validated against the prebuilt-tax.us.1099b schema.
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


def parse_brokerage_1099_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["Brokerage1099Data"]:  # noqa: F821 — imported at runtime
    """
    Send a brokerage composite 1099 PDF to Azure Document Intelligence and
    return a populated Brokerage1099Data.

    Returns None on any error (network, auth, timeout, parse failure) so the
    caller can fall back to the local regex result without crashing.
    """
    if not _AZURE_AVAILABLE:
        logger.warning(
            "azure-ai-formrecognizer is not installed. "
            "Run: pip install azure-ai-formrecognizer"
        )
        return None

    from src.models import Brokerage1099Data

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
        )

        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.1099b", fh)
        result = poller.result()

    except FileNotFoundError:
        logger.warning("azure_1099: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_1099: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_1099: unexpected error: %s", exc)
        return None

    if not result.documents:
        logger.debug("azure_1099: no documents returned for %s", file_path.name)
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

    # Critical fields for confidence scoring (10 fields)
    critical = [
        _str("PayerName"),           # broker_name
        _str("AccountNumber"),       # account_number
        _float("TotalOrdinaryDividends"),
        _float("QualifiedDividends"),
        _float("InterestIncome"),
        _float("GrossProceeds"),
        _float("CostBasis"),
        _float("WashSaleDisallowed"),
        _float("ShortTermGainOrLoss"),
        _float("LongTermGainOrLoss"),
    ]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / 10), 2)

    b_summary: dict = {}
    if _float("GrossProceeds") is not None:
        b_summary["proceeds"] = _float("GrossProceeds")
    if _float("CostBasis") is not None:
        b_summary["cost_basis"] = _float("CostBasis")
    if _float("WashSaleDisallowed") is not None:
        b_summary["wash_sales"] = _float("WashSaleDisallowed")
    if _float("ShortTermGainOrLoss") is not None:
        b_summary["short_term_gain_loss"] = _float("ShortTermGainOrLoss")
    if _float("LongTermGainOrLoss") is not None:
        b_summary["long_term_gain_loss"] = _float("LongTermGainOrLoss")

    data = Brokerage1099Data(
        broker_name=_str("PayerName"),
        account_number=_str("AccountNumber"),
        year=_int("TaxYear"),
        div_ordinary=_float("TotalOrdinaryDividends"),
        div_qualified=_float("QualifiedDividends"),
        div_cap_gain_distributions=_float("TotalCapitalGainDistributions"),
        div_foreign_tax_paid=_float("ForeignTaxPaid"),
        div_section_199a=_float("Section199ADividends"),
        int_interest_income=_float("InterestIncome"),
        int_us_treasury=_float("USTreasuryObligations"),
        section_1256_net_gain_loss=_float("AggregateProfit"),
        b_short_term_covered=_float("ShortTermCoveredProceeds"),
        b_short_term_noncovered=_float("ShortTermNoncoveredProceeds"),
        b_long_term_covered=_float("LongTermCoveredProceeds"),
        b_long_term_noncovered=_float("LongTermNoncoveredProceeds"),
        b_summary=b_summary,
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_1099: extracted %s with confidence %.2f for %s",
        data.broker_name or "unknown broker",
        azure_confidence,
        file_path.name,
    )
    return data
