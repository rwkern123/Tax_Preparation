from __future__ import annotations

import logging
import re

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text, parse_amount_token
from src.models import W2Data

_log = logging.getLogger(__name__)

_NON_NEGATIVE_FIELDS = [
    "box1_wages", "box2_fed_withholding", "box3_ss_wages",
    "box4_ss_tax", "box5_medicare_wages", "box6_medicare_tax",
    "box16_state_wages", "box17_state_tax",
]

_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","IA","ID","IL","IN",
    "KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC","ND","NE","NH",
    "NJ","NM","NV","NY","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VA",
    "VT","WA","WI","WV","WY",
}

# Valid IRS box-12 codes — restricts bare-code extraction to avoid false positives.
_BOX12_CODES = frozenset({
    "A","B","C","D","E","EE","F","G","H","HH",
    "J","K","L","M","N","P","Q","R","S","T","V","W","Y","Z",
    "AA","BB","CC","DD",
})

# SS and Medicare withholding rates used for positional box identification.
_SS_RATE = 0.062
_SS_TOL = 0.005
_MEDI_RATE = 0.0145
_MEDI_TOL = 0.003


def _extract_box12(text: str) -> dict[str, float]:
    """Extract all box 12 code/value pairs from W2 text.

    Handles multiple PDF layouts via four passes (first match wins per code):

    Pass A — Dayforce labeled style: "Code DD  6618.00" inline
    Pass B — WEBB labeled style: "12a Code See inst.\\nD 4686.12" multi-line
    Pass C — Legacy/test style: "Box 12 D 6000.00" or "12 D 6000.00"
    Pass D — Real PDF bare style: "D 4686.12" at start of line (no prefix).
              Uses _BOX12_CODES allowlist to avoid false positives.
    """
    result: dict[str, float] = {}

    # Scope search to the box-12 block when markers exist.
    scope_match = re.search(
        r"(12[a-d]\b[\s\S]*?)(?=\b14\s+Other\b|\b15\s+State\b|\Z)",
        text, re.IGNORECASE,
    )
    scope = scope_match.group(1) if scope_match else text

    # Pass A — Dayforce inline style: "Code DD  6618.00"
    # Run on the full text (not just scope) because OCR of image W2s can place
    # box-12 code/value pairs on the same line as "15 State" headers, pushing
    # them outside the scope boundary.
    for m in re.finditer(
        r"\bCode\s+([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        text, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    # Pass B — WEBB labeled style: "12x Code [optional text]\n DD  9664.46"
    for m in re.finditer(
        r"12[a-d]\s+(?:Code|See\s+inst[^\n]*)[\s]*\n\s*([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        scope, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    # Pass C — legacy/test style: "12 D 6000.00" or "Box 12 D 6000.00"
    for m in re.finditer(
        r"(?:Box\s+)?12\s+([A-Z]{1,2})\s+(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)",
        scope, re.IGNORECASE,
    ):
        code = m.group(1).upper()
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    # Pass D — real PDF bare style: "D 4686.12" or "DD 9664.46" at the start of
    # a line (no "Code" or "12x" prefix).  Only fires for known IRS box-12 codes.
    for m in re.finditer(
        r"(?m)^[ \t]*([A-Z]{1,2})[ \t]+(\d[\d,]*\.\d{2})",
        scope,
    ):
        code = m.group(1).upper()
        if code not in _BOX12_CODES:
            continue
        val = parse_amount_token(m.group(2))
        if val is not None and code not in result:
            result[code] = val

    return result


def _detect_box13(text: str) -> bool:
    """Detect whether the box-13 retirement plan checkbox is checked.

    Two strategies:
    1. Labeled (test/synthetic PDFs): "Retirement ... plan ... X"
    2. Real PDFs: standalone 'X' line within 300 chars of a box-12 entry.
       pdfplumber extracts only the X mark — no checkbox label — so proximity
       to box-12 code/value pairs is used as the locating heuristic.
    """
    # Labeled format
    if re.search(r"Retirement[\s\S]{0,30}plan[\s\S]{0,60}?\bX\b", text, re.IGNORECASE):
        return True

    # Real PDF format: standalone X near box-12 entries.
    box12_positions = [
        m.start()
        for m in re.finditer(r"(?m)^[ \t]*[A-Z]{1,2}[ \t]+\d[\d,]*\.\d{2}", text)
        if m.group(0).strip().split()[0].upper() in _BOX12_CODES
    ]
    if not box12_positions:
        return False

    # Allow "X" or "X X" (doubled copies) on a line by themselves.
    x_positions = [
        m.start()
        for m in re.finditer(r"(?m)^[ \t]*X(?:[ \t]+X)*[ \t]*$", text)
    ]
    for xp in x_positions:
        for bp in box12_positions:
            if abs(xp - bp) < 300:
                return True
    return False


def _fill_boxes_positional(data: W2Data, text: str) -> None:
    """Positional fallback extraction for boxes 1–6.

    Real W2 PDFs (Dayforce, WEBB) omit box labels from the pdfplumber text
    stream.  Values appear as adjacent pairs on a line:

        {box1} {box2}   — federal wages / federal withholding
        {box3} {box4}   — SS wages / SS tax  (rate ~6.2 %)
        {box5} {box6}   — Medicare wages / Medicare tax  (rate ~1.45 %)

    Identification strategy
    -----------------------
    1. Dayforce: use "W-2 Wages {B1} {B3} {B5}" 3-value summary line.
    2. Detect B3/B4 by SS tax rate and B5/B6 by Medicare tax rate in all
       unique same-line pairs.
    3. B1/B2: when B1 is already known, search for the pair "{B1} {X}" where
       X is not the SS or Medicare wage.  When B1 is unknown, use the first
       pair not already claimed by B3/B4 or B5/B6.
    """

    # --- Dayforce summary line: "W-2 Wages {B1} {B3} {B5}" ---
    ww = re.search(
        r"W-2\s+Wages[ \t]+(\d[\d,]*\.\d{2})[ \t]+(\d[\d,]*\.\d{2})[ \t]+(\d[\d,]*\.\d{2})",
        text,
    )
    if ww:
        # Always trust the Dayforce summary line — it overrides any label-based
        # extraction that may have picked up wrong values when OCR flattens the
        # two-column form (box-number digits get matched instead of real amounts).
        # Also reset the paired even-boxes so rate-based detection re-fills them.
        data.box1_wages = parse_amount_token(ww.group(1))
        data.box3_ss_wages = parse_amount_token(ww.group(2))
        data.box5_medicare_wages = parse_amount_token(ww.group(3))
        data.box2_fed_withholding = None
        data.box4_ss_tax = None
        data.box6_medicare_tax = None

    # --- Collect all unique {amount} {amount} pairs (same line only) ---
    all_pairs: list[tuple[float, float]] = []
    seen_pairs: set[tuple[float, float]] = set()
    for m in re.finditer(r"(\d[\d,]*\.\d{2})[ \t]+(\d[\d,]*\.\d{2})", text):
        v1 = parse_amount_token(m.group(1))
        v2 = parse_amount_token(m.group(2))
        if v1 is not None and v2 is not None:
            pair = (v1, v2)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_pairs.append(pair)

    # --- Identify B3/B4 via SS tax rate (~6.2 %) ---
    b3_pair: tuple[float, float] | None = None
    if data.box3_ss_wages is None or data.box4_ss_tax is None:
        for v1, v2 in all_pairs:
            if v1 > 0 and abs(v2 / v1 - _SS_RATE) < _SS_TOL:
                b3_pair = (v1, v2)
                break
        if b3_pair:
            if data.box3_ss_wages is None:
                data.box3_ss_wages = b3_pair[0]
            if data.box4_ss_tax is None:
                data.box4_ss_tax = b3_pair[1]
    if b3_pair is None and data.box3_ss_wages is not None:
        b3_pair = (data.box3_ss_wages, data.box4_ss_tax)  # type: ignore[arg-type]

    # --- Identify B5/B6 via Medicare tax rate (~1.45 %) ---
    b5_pair: tuple[float, float] | None = None
    if data.box5_medicare_wages is None or data.box6_medicare_tax is None:
        for v1, v2 in all_pairs:
            if v1 > 0 and abs(v2 / v1 - _MEDI_RATE) < _MEDI_TOL:
                b5_pair = (v1, v2)
                break
        if b5_pair:
            if data.box5_medicare_wages is None:
                data.box5_medicare_wages = b5_pair[0]
            if data.box6_medicare_tax is None:
                data.box6_medicare_tax = b5_pair[1]
    if b5_pair is None and data.box5_medicare_wages is not None:
        b5_pair = (data.box5_medicare_wages, data.box6_medicare_tax)  # type: ignore[arg-type]

    # --- Identify B1/B2 ---
    excluded: set[tuple[float, float]] = set()
    if b3_pair:
        excluded.add(b3_pair)
    if b5_pair:
        excluded.add(b5_pair)

    if data.box1_wages is None and data.box2_fed_withholding is None:
        # Neither known: take first pair not claimed by B3/B4 or B5/B6.
        for v1, v2 in all_pairs:
            if (v1, v2) not in excluded:
                data.box1_wages = v1
                data.box2_fed_withholding = v2
                break
    elif data.box1_wages is not None and data.box2_fed_withholding is None:
        # B1 already known (e.g. from Dayforce summary); find B2 as the amount
        # paired with B1 on the same line, skipping SS/Medicare wage values.
        b1_str = f"{data.box1_wages:.2f}"
        skip_vals = {data.box3_ss_wages, data.box5_medicare_wages} - {None}
        for m in re.finditer(
            rf"{re.escape(b1_str)}[ \t]+(\d[\d,]*\.\d{{2}})", text
        ):
            candidate = parse_amount_token(m.group(1))
            if candidate not in skip_vals:
                data.box2_fed_withholding = candidate
                break


def _dedupe_doubled(s: str) -> str:
    """Remove doubled text (e.g. 'FOO BAR  FOO BAR' → 'FOO BAR').

    Real W2 PDFs render two side-by-side copies so address lines can appear
    as 'HOUSTON TX 77019 HOUSTON TX 77019'.  We check the two halves
    (±1 char to handle odd lengths) and return the first half when they match.
    """
    s = s.strip()
    n = len(s)
    for split in (n // 2 - 1, n // 2, n // 2 + 1):
        if 0 < split < n:
            first = s[:split].strip()
            second = s[split:].strip()
            if first and first == second:
                return first
    return s


def _parse_csz(line: str) -> tuple[str | None, str | None, str | None]:
    """Parse 'City[,] ST 12345[-4]' into (city, state, zip).

    Handles doubled copies produced by two-column W2 PDFs.
    Returns (None, None, None) if the line doesn't match.
    """
    line = _dedupe_doubled(line)
    m = re.match(
        r"^([\w][\w\s.\-']*?),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$",
        line,
    )
    if m and m.group(2) in _US_STATES:
        return m.group(1).strip(), m.group(2), m.group(3)
    return None, None, None


def _find_csz(lines: list[str]) -> tuple[int, str | None, str | None, str | None]:
    """Return (index, city, state, zip) of the first matching CSZ line."""
    for i, line in enumerate(lines):
        # Strip trailing amount data before parsing (e.g. Dayforce puts amounts
        # on the same line as the CSZ: "Tampa FL 33607 168600.00 10453.20").
        clean = re.sub(r"(?:\s+\d[\d,]*\.\d{2})+\s*$", "", line).strip()
        city, state, zip_ = _parse_csz(clean)
        if state:
            return i, city, state, zip_
    return -1, None, None, None


def _street_before(lines: list[str], csz_idx: int) -> str | None:
    """Return the street line that precedes a CSZ line, if it looks like one."""
    for j in range(csz_idx - 1, max(csz_idx - 4, -1), -1):
        candidate = _dedupe_doubled(lines[j]).strip()
        if candidate and re.match(r"^\d", candidate) and not re.search(r"\.\d{2}", candidate):
            # OCR of image W2s concatenates adjacent-column box labels onto the
            # same line as the street address.  Trim at the first W2 box keyword.
            candidate = re.split(
                r'\s+\d+\s+(?:Social|Medicare|Federal|Wages|State|Employer)',
                candidate,
            )[0].strip()
            return candidate or None
    return None


def _extract_employer_address(
    text: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract employer (street, city, state, zip) from W2 text.

    Pass A — Labeled multi-line block: box 'c' header then name / street / CSZ.
    Pass B — Inline labeled field: 'Employer's address: ...'
    Pass C — Positional: search the ~300 chars surrounding the EIN.
    """
    # Pass A — "c Employer's name, address..." block (labeled/synthetic PDFs)
    m = re.search(
        r"(?:c\s+)?Employer(?:'s)?\s+name[,\s][^\n]*\n([^\n]+)\n([^\n]+)\n([^\n]+)",
        text, re.IGNORECASE,
    )
    if m:
        candidates = [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()]
        idx, city, state, zip_ = _find_csz(candidates)
        if state:
            return _street_before(candidates, idx), city, state, zip_

    # Pass B — Explicit address label
    addr_m = re.search(
        r"Employer(?:'s)?\s+(?:address|street)[^\n:]*:\s*(.+)",
        text, re.IGNORECASE,
    )
    if addr_m:
        street = addr_m.group(1).strip() or None
        rest_lines = [
            l.strip()
            for l in text[addr_m.end(): addr_m.end() + 200].split("\n")
            if l.strip()
        ]
        city, state, zip_ = _parse_csz(rest_lines[0]) if rest_lines else (None, None, None)
        return street, city, state, zip_

    # Pass C — Positional: use EIN as anchor for the employer block
    ein_m = re.search(r"\b\d{2}-\d{7}\b", text)
    if ein_m:
        scope_start = max(0, ein_m.start() - 400)
        scope_lines = [
            l.strip()
            for l in text[scope_start: ein_m.end() + 600].split("\n")
            if l.strip()
        ]
        idx, city, state, zip_ = _find_csz(scope_lines)
        if state:
            return _street_before(scope_lines, idx), city, state, zip_

    return None, None, None, None


def _extract_employee_address(
    text: str,
    employee_name: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract employee (street, city, state, zip) from W2 text.

    Pass A — Labeled field: 'Employee's address: ...'
    Pass B — Positional: lines immediately after the employee name.
    Pass C — Pattern: name \\n street \\n CSZ across the whole text.
    """
    # Pass A — Explicit label
    addr_m = re.search(
        r"Employee(?:'s)?\s+(?:address|street)[^\n:]*:\s*(.+)",
        text, re.IGNORECASE,
    )
    if addr_m:
        street = addr_m.group(1).strip() or None
        rest_lines = [
            l.strip()
            for l in text[addr_m.end(): addr_m.end() + 200].split("\n")
            if l.strip()
        ]
        city, state, zip_ = _parse_csz(rest_lines[0]) if rest_lines else (None, None, None)
        return street, city, state, zip_

    # Pass B — Positional: search after employee name
    if employee_name:
        name_m = re.search(re.escape(employee_name.strip()), text, re.IGNORECASE)
        if name_m:
            lines = [
                l.strip()
                for l in text[name_m.end(): name_m.end() + 400].split("\n")
                if l.strip()
            ]
            idx, city, state, zip_ = _find_csz(lines)
            if state:
                return _street_before(lines, idx), city, state, zip_

    # Pass C — Pattern: name immediately followed by street then CSZ
    pm = re.search(
        r"\n[A-Z][A-Za-z]+(?:[ \t]+[A-Z]\.?)?[ \t]+[A-Z][A-Za-z]+"
        r"\n(\d[^\n]*)\n([\w][\w\s.\-']*,?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?)",
        text,
    )
    if pm:
        city, state, zip_ = _parse_csz(pm.group(2))
        if state:
            return _dedupe_doubled(pm.group(1)).strip(), city, state, zip_

    return None, None, None, None


def _extract_employer_name(text: str) -> str | None:
    """Extract employer name from W2 text.

    Tries label-based patterns first (labeled/synthetic PDFs), then falls back
    to a positional search for the first line containing a company-type suffix
    (Inc, LLC, LLP, Corp, Company) after the first dollar amount.
    """
    # Label-based (labeled PDFs)
    m = re.search(
        r"(?:c\s+)?Employer(?:'s)?\s+name[^\n]*\n\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"Employer(?:'s)?\s+name[^\n:]*:\s*(.+)",
            text, re.IGNORECASE,
        )
    if m:
        candidate = m.group(1).strip()
        # OCR of image W2s (Dayforce) places box-value lines before the employer
        # name because the two-column layout is flattened left-to-right.  If the
        # captured line is all amounts/punctuation, scan forward for the real name.
        if re.match(r'^[\d\s,.()\-]+$', candidate):
            rest = text[m.end(): m.end() + 300]
            for ln in rest.split('\n'):
                ln = ln.strip()
                if ln and not re.match(r'^[\d\s,.()\-]+$', ln):
                    candidate = ln
                    break
        return candidate[:120]

    # Positional: first line with a company suffix after the first dollar amount.
    # [^\n\d]*? ensures no digits appear before the suffix (filters numeric lines).
    first_amount = re.search(r"\d[\d,]+\.\d{2}", text)
    search_start = first_amount.start() if first_amount else 0
    pm = re.search(
        r"(?m)^([^\n\d]*?(?:Inc\b|LLC|LLP|Corp\b|Company\b|Co\.\s).*)$",
        text[search_start:],
        re.IGNORECASE,
    )
    if pm:
        raw = pm.group(1).strip()
        # Trim after the first legal-entity suffix to remove doubled-copy noise
        # (e.g. "The Companies, Inc. The Companies, Inc." → "The Companies, Inc.").
        # Check specific suffixes (LLC/LLP/Inc/Corp) before the generic "Company"
        # so that "Cool Company LLP" is trimmed at "LLP", not at "Company".
        # No trailing \b — it fails after "." since "." is \W.  Use negative
        # lookahead (?![a-zA-Z]) to avoid matching inside "Incorporated" etc.
        suf = re.search(r"\b(?:Inc\.?|LLC|LLP|Corp\.?)(?![a-zA-Z])", raw, re.IGNORECASE)
        if not suf:
            suf = re.search(r"\bCompany\b", raw, re.IGNORECASE)
        if suf:
            raw = raw[:suf.end()].strip()
        return raw[:120] or None

    return None


def _extract_employee_name(text: str) -> str | None:
    """Extract employee name from W2 text.

    Tries label-based first, then a positional pattern: a "First [Initial] Last"
    name on a line immediately followed by a digit (start of a street address).
    This targets the cleanest copy in multi-copy PDFs (e.g. Dayforce page 2).
    """
    # Label-based
    m = re.search(
        r"e\s+Employee(?:'s)?\s+(?:first\s+name|name)[^\n]*\n\s*(.+?)(?:\n|$)",
        text, re.IGNORECASE,
    )
    if m:
        name_raw = m.group(1).strip()
        name_raw = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", name_raw)
        return re.sub(r"\s{2,}", " ", name_raw).strip()[:80] or None

    # Positional (doubled copy): real W2 PDFs render two side-by-side copies, so the
    # name line looks like "BRITTANY T WEBB BRITTANY T WEBB\n6311 ...".
    # Use a backreference to capture the first copy only.
    pm = re.search(
        r"\n([A-Z][A-Za-z]+[ \t]+(?:[A-Z]\.?[ \t]+)?[A-Z][A-Za-z]+)[ \t]+\1\n\d",
        text,
    )
    if pm:
        return pm.group(1).strip()[:80]

    # Positional (single copy): "FirstName [Initial] LastName\n<digit>".
    # Handles mixed-case ("Ryan W Keel") and all-caps ("BRITTANY T WEBB").
    pm = re.search(
        r"\n([A-Z][A-Za-z]+[ \t]+(?:[A-Z]\.?[ \t]+)?[A-Z][A-Za-z]+)\n\d",
        text,
    )
    if pm:
        return pm.group(1).strip()[:80]

    return None


def _extract_year(text: str) -> int | None:
    """Extract the tax year from W2 text using a priority-based strategy.

    A valid tax-year token is NOT preceded by / $ ( or a digit, and NOT
    followed by . or a digit (ruling out date strings and decimal amounts).

    Priority:
    1. "Form W-2 Wage and Tax Statement <year>" — canonical form footer/header.
    2. Year adjacent to any "W-2" label        — shorter label variants.
    3. Standalone year on its own line          — Dayforce / real-PDF layout.
    4. First clean year token in the text       — last resort.
    """
    _YEAR = r"(?<![/$(\d])(20\d{2})(?![.\d])"

    # 1. Full form title (year appears to the right on the same line).
    m = re.search(
        r"Form\s+W-?\s*2\s+Wage\s+and\s+Tax\s+Statement[^\n]{0,40}" + _YEAR,
        text, re.IGNORECASE,
    )
    if m:
        return int(m.group(1))

    # 2. Shorter "W-2" / "W2" label with year nearby (either side, same line).
    m = re.search(r"W-?\s*2\b[^\n]{0,40}" + _YEAR, text, re.IGNORECASE)
    if not m:
        m = re.search(_YEAR + r"[^\n]{0,40}\bW-?\s*2\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # 3. Standalone year on its own line (Dayforce prints "2024" alone).
    m = re.search(r"(?m)^\s*(20\d{2})\s*$", text)
    if m:
        return int(m.group(1))

    # 4. First clean year token anywhere in the text.
    m = re.search(_YEAR, text)
    if m:
        return int(m.group(1))

    return None


def parse_w2_text(text: str, fallback_year: int | None = None) -> W2Data:
    data = W2Data()
    text = normalize_extracted_text(text)

    # --- Year ---
    data.year = _extract_year(text)
    if data.year is None and fallback_year is not None:
        data.year = fallback_year

    # --- EIN ---
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    if ein_match:
        data.employer_ein = ein_match.group(1)

    # --- Employer name ---
    data.employer_name = _extract_employer_name(text)

    # --- Employee name ---
    data.employee_name = _extract_employee_name(text)

    # --- Wage / tax boxes 1–6 (label-based first) ---
    # Patterns require the full field-name keyword after the box number so that
    # column-header lines like "Federal Box 1 Soc. Sec. Box 3 & 7 Medicare Box 5"
    # do not produce false matches.
    data.box1_wages = extract_amount_after_label(
        r"(?:(?:Box\s*[1Il]|1\.?)\s+Wages(?:,?\s*tips)?)",
        text,
    )
    data.box2_fed_withholding = extract_amount_after_label(
        r"(?:2\.?\s*Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?|"
        r"Box\s*2\s+Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?)",
        text,
    )
    data.box3_ss_wages = extract_amount_after_label(
        r"(?:3\.?\s*Social\s+security\s+wages|Box\s*3\s+Social)",
        text,
    )
    data.box4_ss_tax = extract_amount_after_label(
        r"(?:4\.?\s*Social\s+security\s+tax|Box\s*4\s+Social)",
        text,
    )
    data.box5_medicare_wages = extract_amount_after_label(
        r"(?:5\.?\s*Medicare\s+wages|Box\s*5\s+Medicare)",
        text,
    )
    data.box6_medicare_tax = extract_amount_after_label(
        r"(?:6\.?\s*Medicare\s+tax|Box\s*6\s+Medicare)",
        text,
    )

    # Discard negative values from label extraction before the positional fallback
    # so that OCR artifacts like "-214175.64" (a "-" prefix before a value) turn
    # into None and correctly trigger the fallback rather than blocking it.
    for field_name in _NON_NEGATIVE_FIELDS:
        val = getattr(data, field_name)
        if val is not None and val < 0:
            _log.warning("w2: negative value %s for %s — discarding (likely parse error)", val, field_name)
            setattr(data, field_name, None)

    # Positional fallback when any box 1–6 field is still missing.
    if any(v is None for v in [
        data.box1_wages, data.box2_fed_withholding,
        data.box3_ss_wages, data.box4_ss_tax,
        data.box5_medicare_wages, data.box6_medicare_tax,
    ]):
        _fill_boxes_positional(data, text)

    # --- Box 12 ---
    data.box12 = _extract_box12(text)

    # --- Box 13 ---
    data.box13_retirement_plan = _detect_box13(text)

    # --- State boxes 15–17 ---
    # require_decimal=True prevents matching bare box numbers (e.g. "17" or "13") when
    # the state fields are blank — common for employees in no-income-tax states like TX.
    data.box16_state_wages = extract_amount_after_label(r"(?:Box\s*16|16\.?\s*State\s*wages)", text, require_decimal=True)
    data.box17_state_tax = extract_amount_after_label(r"(?:Box\s*17|17\.?\s*State\s*income\s*tax)", text, require_decimal=True)

    # --- Employer address ---
    (
        data.employer_address,
        data.employer_city,
        data.employer_state,
        data.employer_zip,
    ) = _extract_employer_address(text)

    # --- Employee address ---
    (
        data.employee_address,
        data.employee_city,
        data.employee_state,
        data.employee_zip,
    ) = _extract_employee_address(text, data.employee_name)

    # --- Confidence scoring (9 key fields) ---
    populated = sum(
        1 for v in [
            data.employer_name,
            data.employer_ein,
            data.employee_name,
            data.box1_wages,
            data.box2_fed_withholding,
            data.box3_ss_wages,
            data.box4_ss_tax,
            data.box5_medicare_wages,
            data.box6_medicare_tax,
        ]
        if v not in (None, "")
    )
    critical_bonus = 0.1 if data.box1_wages is not None else 0.0
    data.confidence = round(min(1.0, populated / 9 + critical_bonus), 2)
    return data
