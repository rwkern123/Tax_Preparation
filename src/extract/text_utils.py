from __future__ import annotations

import re
from typing import Optional


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
    is_negative = token.startswith("(") and token.endswith(")") or token.startswith("-")
    cleaned = token.replace("$", "").replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
    try:
        value = float(cleaned)
        return -value if is_negative and value > 0 else value
    except ValueError:
        return None


def extract_amount_after_label(label_pattern: str, text: str) -> Optional[float]:
    m = re.search(label_pattern + r"[^\d\-\($]{0,30}(\(?-?\$?\s*[\d,]+(?:\.\d{2})?\)?)", text, re.IGNORECASE)
    if not m:
        return None
    return parse_amount_token(m.group(1))
