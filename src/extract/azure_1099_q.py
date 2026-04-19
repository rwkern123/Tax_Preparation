"""
Azure Document Intelligence opt-in extraction for Form 1099-Q.

NOTE: As of 2025, Azure Document Intelligence does not publish a dedicated
prebuilt-tax.us.1099Q model. This module uses the generic prebuilt-layout
model and maps the extracted key-value pairs to Form1099QData on a best-effort
basis. Field names may need adjustment after live testing.
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


def parse_1099_q_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["Form1099QData"]:  # noqa: F821
    """
    Best-effort extraction via prebuilt-layout. Returns None on any error so
    the caller falls back to the local regex result.
    """
    if not _AZURE_AVAILABLE:
        logger.warning("azure-ai-formrecognizer is not installed.")
        return None

    from src.models import Form1099QData

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(api_key)
        )
        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-layout", fh)
        result = poller.result()
    except FileNotFoundError:
        logger.warning("azure_1099_q: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_1099_q: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_1099_q: unexpected error: %s", exc)
        return None

    # Flatten all key-value pairs from the layout result into a simple dict.
    kv: dict[str, str] = {}
    for page in result.pages or []:
        pass  # prebuilt-layout returns key-value pairs at the document level
    for kv_pair in result.key_value_pairs or []:
        if kv_pair.key and kv_pair.value:
            key = (kv_pair.key.content or "").strip().lower()
            val = (kv_pair.value.content or "").strip()
            kv[key] = val

    def _kv_float(key_fragment: str) -> Optional[float]:
        for k, v in kv.items():
            if key_fragment.lower() in k:
                cleaned = re.sub(r"[,$]", "", v).strip()
                try:
                    return float(cleaned)
                except ValueError:
                    pass
        return None

    def _kv_str(key_fragment: str) -> Optional[str]:
        for k, v in kv.items():
            if key_fragment.lower() in k:
                return v[:120]
        return None

    gross = _kv_float("gross distribution")
    earnings = _kv_float("earnings")
    basis = _kv_float("basis")

    critical = [gross, earnings, basis]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / max(len(critical), 1)), 2)

    # Layout confidence is capped lower than dedicated models since field mapping
    # is heuristic.
    azure_confidence = round(azure_confidence * 0.8, 2)

    if azure_confidence == 0.0:
        return None

    data = Form1099QData(
        payer_name=_kv_str("trustee") or _kv_str("payer"),
        recipient_name=_kv_str("recipient"),
        box1_gross_distribution=gross,
        box2_earnings=earnings,
        box3_basis=basis,
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_1099_q: layout-based extraction confidence %.2f for %s",
        azure_confidence, file_path.name,
    )
    return data
