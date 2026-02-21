from __future__ import annotations

import re
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
    hits = sum(1 for p in patterns if re.search(p, haystack, re.IGNORECASE))
    return min(1.0, hits / max(1, len(patterns)) + (0.2 if hits else 0.0))


def detect_year(text: str) -> int | None:
    years = re.findall(r"\b(20\d{2})\b", text)
    for y in years:
        val = int(y)
        if 2000 <= val <= 2100:
            return val
    return None


def classify_document(file_path: Path, text: str) -> tuple[str, float, int | None]:
    haystack = f"{file_path.name}\n{text[:4000]}"
    scores = {
        "w2": _score(W2_PATTERNS, haystack),
        "brokerage_1099": _score(BROKER_PATTERNS, haystack),
        "form_1098": _score(FORM_1098_PATTERNS, haystack),
    }

    doc_type, confidence = max(scores.items(), key=lambda kv: kv[1])
    if confidence < 0.35:
        return "unknown", round(confidence * 0.8, 2), detect_year(haystack)
    return doc_type, round(confidence, 2), detect_year(haystack)
