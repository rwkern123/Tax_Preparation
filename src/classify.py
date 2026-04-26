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
FORM_1099_NEC_PATTERNS = [r"1099-nec", r"1099\s*nec", r"nonemployee\s+compensation", r"non-?employee\s+compensation"]
FORM_1099_R_PATTERNS = [r"1099-r\b", r"1099\s*-?\s*r\b", r"distributions?\s+from\s+pensions?", r"gross\s+distribution", r"IRA\s*/\s*SEP\s*/\s*SIMPLE"]
FORM_1099_G_PATTERNS = [r"1099-g\b", r"1099\s*-?\s*g\b", r"unemployment\s+compensation", r"state\s+or\s+local\s+income\s+tax\s+refund", r"certain\s+government\s+payments"]
FORM_1099_MISC_PATTERNS = [r"1099-misc\b", r"1099\s*-?\s*misc\b", r"miscellaneous\s+(?:income|information)", r"\broyalties\b", r"gross\s+proceeds\s+paid\s+to\s+an?\s+attorney"]
FORM_1098_T_PATTERNS = [r"1098-t\b", r"1098\s*-?\s*t\b", r"tuition\s+statement", r"qualified\s+tuition", r"scholarships?\s+or\s+grants?", r"half[-\s]time\s+student"]
FORM_1099_Q_PATTERNS = [r"1099-q\b", r"1099\s*-?\s*q\b", r"qualified\s+education\s+program", r"section\s+529", r"coverdell\s+esa", r"529\s+plan"]
FORM_1099_SA_PATTERNS = [r"1099-sa\b", r"1099\s*-?\s*sa\b", r"distributions?\s+from\s+(?:an?\s+)?hsa", r"health\s+savings\s+account", r"archer\s+msa", r"medicare\s+advantage\s+msa"]
PRIOR_YEAR_RETURN_PATTERNS = [r"\bform\s*1040\b", r"\b1040\b", r"adjusted\s+gross\s+income", r"taxable\s+income", r"total\s+tax", r"federal\s+tax\s+return"]
SSA_1099_PATTERNS = [
    r"\bssa[-\s]?1099\b",
    r"social\s+security\s+benefit\s+statement",
    r"social\s+security\s+administration",
    r"net\s+(?:social\s+security\s+)?benefits?",
    r"benefits?\s+paid.*benefits?\s+repaid",
]


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
        "form_1099_nec": _score(FORM_1099_NEC_PATTERNS, haystack),
        "form_1099_r": _score(FORM_1099_R_PATTERNS, haystack),
        "form_1099_g": _score(FORM_1099_G_PATTERNS, haystack),
        "form_1099_misc": _score(FORM_1099_MISC_PATTERNS, haystack),
        "form_1098_t": _score(FORM_1098_T_PATTERNS, haystack),
        "form_1099_q": _score(FORM_1099_Q_PATTERNS, haystack),
        "form_1099_sa": _score(FORM_1099_SA_PATTERNS, haystack),
        "prior_year_return": _score(PRIOR_YEAR_RETURN_PATTERNS, haystack),
        "ssa_1099": _score(SSA_1099_PATTERNS, haystack),
    }

    doc_type, confidence = max(scores.items(), key=lambda kv: kv[1])
    if confidence < 0.25:
        return "unknown", round(confidence * 0.8, 2), detect_year(haystack)
    return doc_type, round(confidence, 2), detect_year(haystack)
