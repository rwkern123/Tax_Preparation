"""
parser_bridge.py — wraps src/ parsers and returns a normalized result dict.
This is the only file in preparer/ that imports from src/.
"""
from pathlib import Path
from dataclasses import asdict


_BROKERAGE_CATEGORIES = {"1099_INT", "1099_DIV", "1099_B", "Brokerage_1099"}


def parse_uploaded_file(file_path: str, use_ocr: bool = False, category_hint: str = "") -> dict:
    """
    Parse a single file and return a normalized result dict:
    {
        "doc_type": str,
        "confidence": float,
        "parsing_status": "done" | "failed",
        "parse_error": str | None,
        "extracted": dict,   # raw parser output sliced into ExtractionResult shape
        "drake": dict,       # Drake-normalized field names (for Phase 2 RPA)
        "flags": list[dict], # review flags
    }
    """
    path = Path(file_path)
    try:
        from src.extract.generic_pdf import get_document_text
        from src.classify import classify_document
        from src.extract.w2 import parse_w2_text
        from src.extract.brokerage_1099 import parse_brokerage_1099_text
        from src.extract.form_1098 import parse_1098_text
        from src.extract.form_1099b_trades import parse_1099b_trades_text

        text, _notes = get_document_text(path, enable_ocr=use_ocr)
        doc_type, confidence, _year = classify_document(path, text)

        # If the upload category implies a brokerage form but classification didn't
        # pick it up (e.g. low-confidence composite PDF), force brokerage parsing.
        if category_hint in _BROKERAGE_CATEGORIES and doc_type != "brokerage_1099":
            doc_type = "brokerage_1099"
            confidence = max(confidence, 0.5)

        extracted: dict = {}
        if doc_type == "w2":
            data = parse_w2_text(text)
            extracted = {"w2": [asdict(data)]}
        elif doc_type == "brokerage_1099":
            summary = parse_brokerage_1099_text(text)
            trades = parse_1099b_trades_text(text)
            extracted = {
                "brokerage_1099": [asdict(summary)],
                "brokerage_1099_trades": [asdict(t) for t in trades],
            }
        elif doc_type == "form_1098":
            data = parse_1098_text(text)
            extracted = {"form_1098": [asdict(data)]}
        elif doc_type == "prior_year_return":
            from src.extract.prior_year_return import parse_prior_year_return_text
            data = parse_prior_year_return_text(text)
            extracted = {"prior_year_return": [asdict(data)]}

        drake = _to_drake_fields(doc_type, extracted)
        flags = _generate_flags(doc_type, confidence, extracted)

        return {
            "doc_type": doc_type,
            "confidence": confidence,
            "parsing_status": "done",
            "parse_error": None,
            "extracted": extracted,
            "drake": drake,
            "flags": flags,
        }

    except Exception as exc:
        return {
            "doc_type": "unknown",
            "confidence": 0.0,
            "parsing_status": "failed",
            "parse_error": str(exc),
            "extracted": {},
            "drake": {},
            "flags": [
                {
                    "type": "parse_error",
                    "severity": "error",
                    "message": f"Parsing failed: {exc}",
                    "field": None,
                }
            ],
        }


def azure_parse_uploaded_file(
    file_path: str,
    endpoint: str,
    api_key: str,
    doc_type_hint: str = "unknown",
) -> dict:
    """
    Re-parse a single file using Azure Document Intelligence and return a
    normalized result dict in the same shape as parse_uploaded_file().

    If the azure-ai-formrecognizer SDK is not installed, it is installed
    automatically before proceeding.
    """
    # Auto-install the SDK if missing
    try:
        import azure.ai.formrecognizer  # noqa: F401
    except ImportError:
        import subprocess, sys
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "azure-ai-formrecognizer"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    path = Path(file_path)
    try:
        if doc_type_hint == "w2":
            from src.extract.azure_w2 import parse_w2_azure
            result = parse_w2_azure(path, endpoint, api_key)
            if result is None:
                raise RuntimeError("Azure returned no result for this document.")
            from dataclasses import asdict
            extracted = {"w2": [asdict(result)]}
            doc_type = "w2"
            confidence = result.confidence

        elif doc_type_hint == "brokerage_1099":
            from src.extract.azure_1099 import parse_brokerage_1099_azure
            result = parse_brokerage_1099_azure(path, endpoint, api_key)
            if result is None:
                raise RuntimeError("Azure returned no result for this document.")
            from dataclasses import asdict
            extracted = {"brokerage_1099": [asdict(result)]}
            doc_type = "brokerage_1099"
            confidence = result.confidence

        else:
            raise RuntimeError(
                f"Azure enhancement is only available for W-2 and brokerage 1099 documents "
                f"(this document is classified as '{doc_type_hint}')."
            )

        drake = _to_drake_fields(doc_type, extracted)
        flags = _generate_flags(doc_type, confidence, extracted)

        return {
            "doc_type": doc_type,
            "confidence": confidence,
            "parsing_status": "done",
            "parse_error": None,
            "extracted": extracted,
            "drake": drake,
            "flags": flags,
        }

    except Exception as exc:
        return {
            "doc_type": doc_type_hint if doc_type_hint != "unknown" else "unknown",
            "confidence": 0.0,
            "parsing_status": "failed",
            "parse_error": str(exc),
            "extracted": {},
            "drake": {},
            "flags": [
                {
                    "type": "parse_error",
                    "severity": "error",
                    "message": f"Azure parsing failed: {exc}",
                    "field": None,
                }
            ],
        }


def _to_drake_fields(doc_type: str, extracted: dict) -> dict:
    """Map extracted fields to stable Drake-compatible field names for Phase 2 RPA."""
    if doc_type == "w2" and extracted.get("w2"):
        w = extracted["w2"][0]
        return {
            "w2_employer_name":         w.get("employer_name"),
            "w2_employer_ein":          w.get("employer_ein"),
            "w2_employee_name":         w.get("employee_name"),
            "w2_box1_wages":            w.get("box1_wages"),
            "w2_box2_federal_withheld": w.get("box2_fed_withholding"),
            "w2_box3_ss_wages":         w.get("box3_ss_wages"),
            "w2_box4_ss_tax":           w.get("box4_ss_tax"),
            "w2_box5_medicare_wages":   w.get("box5_medicare_wages"),
            "w2_box6_medicare_tax":     w.get("box6_medicare_tax"),
            "w2_box12":                 w.get("box12", {}),
            "w2_box13_retirement_plan": w.get("box13_retirement_plan"),
            "w2_box16_state_wages":     w.get("box16_state_wages"),
            "w2_box17_state_tax":       w.get("box17_state_tax"),
        }

    if doc_type == "brokerage_1099" and extracted.get("brokerage_1099"):
        b = extracted["brokerage_1099"][0]
        bs = b.get("b_summary") or {}
        return {
            "b1099_broker_name":              b.get("broker_name"),
            "b1099_ordinary_dividends":       b.get("div_ordinary"),
            "b1099_qualified_dividends":      b.get("div_qualified"),
            "b1099_cap_gain_distributions":   b.get("div_cap_gain_distributions"),
            "b1099_foreign_tax_paid":         b.get("div_foreign_tax_paid"),
            "b1099_interest_income":          b.get("int_interest_income"),
            "b1099_us_treasury_interest":     b.get("int_us_treasury"),
            "b1099_proceeds":                 bs.get("proceeds"),
            "b1099_cost_basis":               bs.get("cost_basis"),
            "b1099_wash_sales":               bs.get("wash_sales"),
            "b1099_short_term_gain_loss":     bs.get("short_term_gain_loss"),
            "b1099_long_term_gain_loss":      bs.get("long_term_gain_loss"),
        }

    if doc_type == "form_1098" and extracted.get("form_1098"):
        f = extracted["form_1098"][0]
        return {
            "f1098_lender_name":             f.get("lender_name"),
            "f1098_mortgage_interest":       f.get("mortgage_interest_received"),
            "f1098_points_paid":             f.get("points_paid"),
            "f1098_mortgage_insurance":      f.get("mortgage_insurance_premiums"),
            "f1098_real_estate_taxes":       f.get("real_estate_taxes"),
            "f1098_outstanding_principal":   f.get("mortgage_principal_outstanding"),
        }

    return {}


# Confidence thresholds
_CONFIDENCE_ERROR = 0.30
_CONFIDENCE_WARN  = 0.55

# Required fields per doc type
_REQUIRED_FIELDS: dict[str, list[tuple[str, str]]] = {
    "w2": [
        ("box1_wages",         "Box 1 Wages"),
        ("box2_fed_withholding", "Box 2 Federal Withheld"),
        ("employer_ein",       "Employer EIN"),
        ("employer_name",      "Employer Name"),
    ],
    "brokerage_1099": [
        ("broker_name",        "Broker Name"),
    ],
    "form_1098": [
        ("mortgage_interest_received", "Mortgage Interest"),
        ("lender_name",               "Lender Name"),
    ],
}


def _generate_flags(doc_type: str, confidence: float, extracted: dict) -> list[dict]:
    flags: list[dict] = []

    if confidence < _CONFIDENCE_ERROR:
        flags.append({
            "type": "low_confidence",
            "severity": "error",
            "message": f"Very low extraction confidence ({confidence:.0%}). Manual review required.",
            "field": "confidence",
        })
    elif confidence < _CONFIDENCE_WARN:
        flags.append({
            "type": "low_confidence",
            "severity": "warning",
            "message": f"Low extraction confidence ({confidence:.0%}). Verify extracted fields.",
            "field": "confidence",
        })

    if doc_type == "unknown":
        flags.append({
            "type": "unclassified",
            "severity": "warning",
            "message": "Document could not be classified. Review manually.",
            "field": None,
        })

    required = _REQUIRED_FIELDS.get(doc_type, [])
    records = extracted.get(doc_type, [])
    if required and records:
        rec = records[0]
        for field_key, field_label in required:
            if rec.get(field_key) is None:
                flags.append({
                    "type": "missing_field",
                    "severity": "warning",
                    "message": f"Could not extract '{field_label}'. Verify manually.",
                    "field": field_key,
                })

    return flags
