from __future__ import annotations

import logging
import re
from typing import Optional

_log = logging.getLogger(__name__)


def normalize_extracted_text(text: str) -> str:
    """Normalize noisy OCR/PDF text for downstream regex parsing."""
    if not text:
        return ""
    normalized = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    normalized = normalized.replace("\u00a0", " ")
    # Common OCR substitutions in numeric context.
    normalized = re.sub(r"(?<=\d)[Oo](?=\d)", "0", normalized)
    normalized = re.sub(r"(?<=\bBox\s)[lI](?=\b)", "1", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<=\d)[lI](?=\d)", "1", normalized)
    # Squash repeated whitespace while keeping line boundaries useful.
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


_AMOUNT_RE = re.compile(r"\(?-?\$?\s*([\d,]+(?:\.\d{2})?)\)?")


def parse_amount_token(raw: str) -> Optional[float]:
    if raw is None:
        return None
    token = raw.strip()
    if not token:
        return None
    is_negative = (token.startswith("(") and token.endswith(")")) or token.startswith("-")
    cleaned = token.replace("$", "").replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
    try:
        value = float(cleaned)
        return -value if is_negative and value > 0 else value
    except ValueError:
        return None


def extract_amount_after_label(
    label_pattern: str, text: str, require_decimal: bool = False
) -> Optional[float]:
    # Allow up to 60 chars between label and value to handle wide-column PDF table layouts
    # (pdfplumber linearizes two-column forms, creating large gaps between label and value).
    # When require_decimal=True the matched amount must contain a ".XX" fractional part,
    # which prevents bare integers (e.g. the next box number) from being captured when a
    # field is genuinely empty on the form (common for state boxes on no-income-tax states).
    decimal_part = r"\.\d{2}" if require_decimal else r"(?:\.\d{2})?"
    m = re.search(
        label_pattern + r"[^\d\-\($]{0,60}(\(?-?\$?\s*[\d,]+" + decimal_part + r"\)?)",
        text,
        re.IGNORECASE,
    )
    if not m:
        _log.debug("extract_amount_after_label: no match for pattern %r in %d chars of text", label_pattern, len(text))
        return None
    return parse_amount_token(m.group(1))
