"""
Azure Document Intelligence opt-in extraction for Schedule C (Form 1040).

NOTE: As of 2025, Azure Document Intelligence does not publish a dedicated
prebuilt-tax model for Schedule C. This module uses the generic prebuilt-layout
model and maps extracted key-value pairs to ScheduleCData on a best-effort
basis. Confidence is intentionally capped lower than dedicated-model extractors
since field mapping is heuristic.
"""
from __future__ import annotations

import logging
import re
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


def parse_schedule_c_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["ScheduleCData"]:  # noqa: F821
    """Best-effort extraction via prebuilt-layout. Returns None on any error."""
    if not _AZURE_AVAILABLE:
        logger.warning("azure-ai-formrecognizer is not installed.")
        return None

    from src.models import ScheduleCData

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(api_key)
        )
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-layout", fh)
        result = poller.result()
    except FileNotFoundError:
        logger.warning("azure_schedule_c: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_schedule_c: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_schedule_c: unexpected error: %s", exc)
        return None

    kv: dict[str, str] = {}
    for kv_pair in result.key_value_pairs or []:
        if kv_pair.key and kv_pair.value:
            key = (kv_pair.key.content or "").strip().lower()
            val = (kv_pair.value.content or "").strip()
            kv[key] = val

    def _kv_float(*key_fragments: str) -> Optional[float]:
        for fragment in key_fragments:
            for k, v in kv.items():
                if fragment.lower() in k:
                    cleaned = re.sub(r"[,$()]", "", v).strip()
                    is_negative = "(" in v and ")" in v
                    try:
                        amount = float(cleaned)
                        return -amount if is_negative else amount
                    except ValueError:
                        pass
        return None

    def _kv_str(*key_fragments: str) -> Optional[str]:
        for fragment in key_fragments:
            for k, v in kv.items():
                if fragment.lower() in k:
                    return v[:120]
        return None

    line_1 = _kv_float("gross receipts", "line 1")
    line_7 = _kv_float("gross income", "line 7")
    line_28 = _kv_float("total expenses", "line 28")
    line_31 = _kv_float("net profit", "line 31")

    critical = [line_1, line_7, line_28, line_31]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / max(len(critical), 1)), 2)
    azure_confidence = round(azure_confidence * 0.8, 2)  # cap layout-based extraction

    if azure_confidence == 0.0:
        return None

    data = ScheduleCData(
        proprietor_name=_kv_str("name of proprietor", "proprietor"),
        line_a_principal_business=_kv_str("principal business", "line a"),
        line_b_business_code=_kv_str("business code", "code"),
        line_c_business_name=_kv_str("business name", "line c"),
        line_d_ein=_kv_str("employer id", "ein"),
        line_1_gross_receipts=line_1,
        line_2_returns_allowances=_kv_float("returns and allowances", "line 2"),
        line_4_cogs=_kv_float("cost of goods sold", "line 4"),
        line_7_gross_income=line_7,
        line_8_advertising=_kv_float("advertising", "line 8"),
        line_9_car_truck=_kv_float("car and truck", "line 9"),
        line_13_depreciation_section_179=_kv_float("depreciation", "section 179"),
        line_22_supplies=_kv_float("supplies", "line 22"),
        line_25_utilities=_kv_float("utilities", "line 25"),
        line_28_total_expenses=line_28,
        line_30_home_office=_kv_float("business use of your home", "line 30"),
        line_31_net_profit_loss=line_31,
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_schedule_c: layout-based extraction confidence %.2f for %s",
        azure_confidence, file_path.name,
    )
    return data
