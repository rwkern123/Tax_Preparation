"""
Azure Form Recognizer opt-in extraction for W-2 documents.

Uses the prebuilt-tax.us.w2 model. Only called when --enable-azure is set
and local confidence is below threshold. Falls back gracefully if Azure is
unavailable or returns an error.
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


def parse_w2_azure(
    file_path: Path,
    endpoint: str,
    api_key: str,
) -> Optional["W2Data"]:  # noqa: F821 — imported at runtime
    """
    Send a W-2 PDF to Azure Document Intelligence and return a populated W2Data.

    Returns None on any error (network, auth, timeout, parse failure) so the
    caller can fall back to the local regex result without crashing.
    """
    if not _AZURE_AVAILABLE:
        logger.warning(
            "azure-ai-formrecognizer is not installed. "
            "Run: pip install azure-ai-formrecognizer"
        )
        return None

    from src.models import W2Data

    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key),
        )

        with open(file_path, "rb") as fh:
            poller = client.begin_analyze_document("prebuilt-tax.us.w2", fh)
        result = poller.result()

    except FileNotFoundError:
        logger.warning("azure_w2: file not found: %s", file_path)
        return None
    except (HttpResponseError, ServiceRequestError) as exc:
        logger.warning("azure_w2: Azure request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("azure_w2: unexpected error: %s", exc)
        return None

    if not result.documents:
        logger.debug("azure_w2: no documents returned for %s", file_path.name)
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

    # State fields live in a list; grab the first entry
    def _state_list_str(child: str) -> Optional[str]:
        f = fields.get("StateAndLocalTaxesGroup")
        if f and f.value and isinstance(f.value, list) and len(f.value) > 0:
            entry = f.value[0]
            if hasattr(entry, "value") and entry.value and hasattr(entry.value, "get"):
                sub = entry.value.get(child)
                return sub.value if sub and sub.value is not None else None
        return None

    def _state_list_float(child: str) -> Optional[float]:
        f = fields.get("StateAndLocalTaxesGroup")
        if f and f.value and isinstance(f.value, list) and len(f.value) > 0:
            entry = f.value[0]
            if hasattr(entry, "value") and entry.value and hasattr(entry.value, "get"):
                sub = entry.value.get(child)
                if sub and sub.value is not None:
                    try:
                        return float(
                            str(sub.value).replace(",", "").replace("$", "").strip()
                        )
                    except (ValueError, TypeError):
                        pass
        return None

    # Count populated critical fields for confidence scoring
    critical = [
        _nested_str("Employer", "Name"),
        _nested_str("Employer", "IdNumber"),
        _nested_str("Employee", "Name"),
        _float("WagesTipsAndOtherCompensation"),
        _float("FederalIncomeTaxWithheld"),
        _float("SocialSecurityWages"),
        _float("SocialSecurityTaxWithheld"),
        _float("MedicareWagesAndTips"),
        _float("MedicareTaxWithheld"),
    ]
    populated = sum(1 for v in critical if v is not None)
    azure_confidence = round(min(1.0, populated / 9 + (0.1 if critical[3] is not None else 0)), 2)

    w2 = W2Data(
        employer_name=_nested_str("Employer", "Name"),
        employer_ein=_nested_str("Employer", "IdNumber"),
        employer_address=_nested_str("Employer", "Address"),
        employee_name=_nested_str("Employee", "Name"),
        employee_address=_nested_str("Employee", "Address"),
        box1_wages=_float("WagesTipsAndOtherCompensation"),
        box2_fed_withholding=_float("FederalIncomeTaxWithheld"),
        box3_ss_wages=_float("SocialSecurityWages"),
        box4_ss_tax=_float("SocialSecurityTaxWithheld"),
        box5_medicare_wages=_float("MedicareWagesAndTips"),
        box6_medicare_tax=_float("MedicareTaxWithheld"),
        box13_retirement_plan=bool(_str("StatutoryEmployee")),
        box16_state_wages=_state_list_float("StateWages"),
        box17_state_tax=_state_list_float("StateIncomeTax"),
        confidence=azure_confidence,
        extraction_source="azure",
    )

    logger.debug(
        "azure_w2: extracted %s with confidence %.2f for %s",
        w2.employer_name or "unknown employer",
        azure_confidence,
        file_path.name,
    )
    return w2
