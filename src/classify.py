from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

W2_PATTERNS = [r"w[-_ ]?2", r"form\s*w-?2", r"wage and tax statement"]
BROKER_PATTERNS = [
    r"1099",
    r"1099-div",
    r"1099-int",
    r"1099-b",
    r"composite",
    r"brokerage",
]
FORM_1098_PATTERNS = [r"1098", r"form\s*1098", r"mortgage interest statement", r"mortgage interest received"]


def _score(patterns: list[str], haystack: str) -> float:
    if not patterns:
        return 0.0
    hits = sum(1 for p in patterns if re.search(p, haystack, re.IGNORECASE))
    if hits == 0:
        return 0.0
    return round(min(1.0, hits / len(patterns)), 3)


def detect_year(text: str) -> int | None:
    raw = re.findall(r"\b(20\d{2})\b", text)
    candidates = [int(y) for y in raw if 2000 <= int(y) <= 2100]
    if not candidates:
        return None
    # Most common year is almost always the document's actual tax year.
    return Counter(candidates).most_common(1)[0][0]


def classify_document_structured(file_path: Path) -> tuple[str, float] | None:
    """Classify CSV/XML files by extension and content signatures without full-text extraction.

    Returns (doc_type, confidence) if the file is a recognised structured format,
    or None if the file should fall through to text-based classification.
    """
    ext = file_path.suffix.lower()
    if ext == ".csv":
        try:
            sample = file_path.read_text(encoding="utf-8", errors="replace")[:500]
        except OSError:
            return None
        if re.search(r"form 1099", sample, re.IGNORECASE):
            return ("brokerage_1099", 1.0)
        return None
    if ext == ".xml":
        try:
            sample = file_path.read_text(encoding="utf-8", errors="replace")[:800]
        except OSError:
            return None
        if re.search(r"TAX1099", sample):
            return ("brokerage_1099", 1.0)
        return None
    return None


def classify_document(file_path: Path, text: str) -> tuple[str, float, int | None]:
    # Sample beginning, middle, and end to catch form indicators across all pages
    # without running all patterns against the full text of very large PDFs.
    text_len = len(text)
    if text_len <= 12000:
        sample = text
    else:
        mid = text_len // 2
        sample = text[:4000] + text[mid - 2000:mid + 2000] + text[-4000:]
    haystack = f"{file_path.name}\n{sample}"

    scores = {
        "w2": _score(W2_PATTERNS, haystack),
        "brokerage_1099": _score(BROKER_PATTERNS, haystack),
        "form_1098": _score(FORM_1098_PATTERNS, haystack),
    }

    doc_type, confidence = max(scores.items(), key=lambda kv: kv[1])
    if confidence < 0.25:
        return "unknown", round(confidence * 0.8, 2), detect_year(haystack)
    return doc_type, round(confidence, 2), detect_year(haystack)
