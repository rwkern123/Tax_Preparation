"""
Azure Document Intelligence opt-in extraction for Form 1098-T.

Uses the prebuilt-tax.us.1098T model. Only called when --enable-azure is set
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


def parse_1098_t_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["Form1098TData"]:  # noqa: F821
    if not _AZURE_AVAILABLE:
        logger.warning("azure-ai-formrecognizer is not installed.")
        return None

    from src.models import Form1098TData

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(api_key)
        )
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.1098T", fh)
        result = poller.result()
    except FileNotFoundError:
        logger.warning("azure_1098_t: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_1098_t: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_1098_t: unexpected error: %s", exc)
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

    def _bool(name: str) -> bool:
        f = fields.get(name)
        if f is None or f.value is None:
            return False
        return bool(f.value)

    def _int(name: str) -> Optional[int]:
        f = fields.get(name)
        if f is None or f.value is None:
            return None
        try:
            return int(str(f.value).strip())
        except (ValueError, TypeError):
            return None

    critical = [
        _str("FilerName"),
        _str("StudentName"),
        _float("PaymentsReceived"),
        _float("ScholarshipsOrGrants"),
    ]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / len(critical)), 2)

    data = Form1098TData(
        filer_name=_str("FilerName"),
        filer_tin=_str("FilerTIN"),
        student_name=_str("StudentName"),
        student_tin=_str("StudentTIN"),
        account_number=_str("AccountNumber"),
        year=_int("TaxYear"),
        box1_payments_received=_float("PaymentsReceived"),
        box4_adjustments_prior_year=_float("AdjustmentsMadeForPriorYear"),
        box5_scholarships_grants=_float("ScholarshipsOrGrants"),
        box6_adjustments_scholarships=_float("AdjustmentsToScholarships"),
        box7_prior_year_amount=_bool("Box7"),
        box8_half_time_student=_bool("AtLeastHalfTimeStudent"),
        box9_graduate_student=_bool("GraduateStudent"),
        box10_insurance_reimbursements=_float("InsuranceContractReimbursements"),
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_1098_t: extracted confidence %.2f for %s", azure_confidence, file_path.name
    )
    return data
