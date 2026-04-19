"""
Azure Document Intelligence opt-in extraction for Form 1099-G.

Uses the prebuilt-tax.us.1099G model. Only called when --enable-azure is set
and local confidence is below threshold.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AZURE_CONFIDENCE_THRESHOLD = 0.85

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


def parse_1099_g_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["Form1099GData"]:  # noqa: F821
    if not _AZURE_AVAILABLE:
        logger.warning("azure-ai-formrecognizer is not installed.")
        return None

    from src.models import Form1099GData

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(api_key)
        )
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.1099G", fh)
        result = poller.result()
    except FileNotFoundError:
        logger.warning("azure_1099_g: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_1099_g: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_1099_g: unexpected error: %s", exc)
        return None

    if not result.documents:
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

    critical = [
        _str("PayerName"),
        _str("RecipientName"),
        _float("UnemploymentCompensation"),
        _float("StateTaxWithheld"),
        _float("FederalIncomeTaxWithheld"),
    ]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / len(critical)), 2)

    data = Form1099GData(
        payer_name=_str("PayerName"),
        payer_tin=_str("PayerTIN"),
        recipient_name=_str("RecipientName"),
        recipient_tin=_str("RecipientTIN"),
        account_number=_str("AccountNumber"),
        year=_int("TaxYear"),
        box1_unemployment_compensation=_float("UnemploymentCompensation"),
        box2_state_local_tax_refund=_float("StateOrLocalIncomeTaxRefunds"),
        box4_fed_withholding=_float("FederalIncomeTaxWithheld"),
        box5_rtaa_payments=_float("RTAAPayments"),
        box6_taxable_grants=_float("TaxableGrants"),
        box7_agriculture_payments=_float("AgriculturePayments"),
        box11_state_income_tax_withheld=_float("StateTaxWithheld"),
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_1099_g: extracted confidence %.2f for %s", azure_confidence, file_path.name
    )
    return data
