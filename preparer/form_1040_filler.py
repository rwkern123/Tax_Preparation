"""
Form 1040 filler — aggregates extracted doc data and overlays values onto a flat PDF.

Uses reportlab for coordinate-based text overlay merged via pypdf.
Coordinates derived from pdfplumber inspection of pdf_forms/Form_1040.pdf.
"""
from __future__ import annotations

import io
from typing import Any

# ---------------------------------------------------------------------------
# Field coordinate map for flat PDF overlay
# (page_index, x, y_from_bottom, right_align_width)
# Page 0 = Form 1040 p.1, Page 1 = Form 1040 p.2
# y_from_bottom = 792 - pdfplumber_top
# For right-aligned fields: draw right edge at x, text right-aligned in box of width w
# ---------------------------------------------------------------------------
_PORTRAIT_H = 792.0

# (page_index, right_x, y_from_bottom)  — text is right-aligned up to right_x
_FIELD_COORDS: dict[str, tuple[int, float, float]] = {
    "line_1a":   (0, 569.0, _PORTRAIT_H - 453.0),   # W-2 wages
    "line_1z":   (0, 569.0, _PORTRAIT_H - 560.0),   # Total wages
    "line_2b":   (0, 569.0, _PORTRAIT_H - 573.0),   # Taxable interest
    "line_3a":   (0, 392.0, _PORTRAIT_H - 585.0),   # Qualified dividends (left col)
    "line_3b":   (0, 569.0, _PORTRAIT_H - 597.0),   # Ordinary dividends
    "line_7":    (0, 569.0, _PORTRAIT_H - 693.0),   # Capital gain/loss
    "line_25a":  (1, 392.0, _PORTRAIT_H - 279.0),   # W-2 withholding (mid col)
    "line_25b":  (1, 392.0, _PORTRAIT_H - 291.0),   # 1099 withholding (mid col)
    "line_25d":  (1, 569.0, _PORTRAIT_H - 314.0),   # Total withheld
    "scha_8a":   (2, 569.0, _PORTRAIT_H - 350.0),   # Mortgage interest (Sched A approx)
    "scha_5b":   (2, 569.0, _PORTRAIT_H - 220.0),   # Real estate taxes (Sched A approx)
}


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}"


def aggregate_1040_data(parsed_docs: list[dict], user: dict, year: int) -> dict:
    """
    Aggregate extracted fields across all parsed documents into Form 1040 line values.
    Returns a dict with keys matching _FIELD_COORDS plus metadata.
    Each entry: {"value": float|None, "sources": [str, ...]}
    """
    w2_wages        = 0.0
    w2_withheld     = 0.0
    interest        = 0.0
    ord_dividends   = 0.0
    qual_dividends  = 0.0
    cap_gain        = 0.0
    b_withheld      = 0.0
    mortgage_int    = 0.0
    real_estate_tax = 0.0

    w2_sources:        list[str] = []
    b1099_sources:     list[str] = []
    f1098_sources:     list[str] = []

    has_any = False

    for doc in parsed_docs:
        ej = doc.get("extracted_json") or {}
        name = doc.get("original_name", "unknown")

        # W-2
        for w2 in ej.get("w2", []):
            v1 = w2.get("box1_wages")
            v2 = w2.get("box2_fed_withholding")
            if v1 is not None:
                w2_wages += float(v1)
                has_any = True
            if v2 is not None:
                w2_withheld += float(v2)
                has_any = True
            if v1 is not None or v2 is not None:
                if name not in w2_sources:
                    w2_sources.append(name)

        # Brokerage 1099 summary
        for b in ej.get("brokerage_1099", []):
            vi  = b.get("int_interest_income")
            vod = b.get("div_ordinary")
            vqd = b.get("div_qualified")
            if vi  is not None: interest       += float(vi);  has_any = True
            if vod is not None: ord_dividends  += float(vod); has_any = True
            if vqd is not None: qual_dividends += float(vqd); has_any = True
            if any(x is not None for x in [vi, vod, vqd]):
                if name not in b1099_sources:
                    b1099_sources.append(name)

        # Brokerage 1099 summary gains & withholding
        for b in ej.get("brokerage_1099", []):
            bs = b.get("b_summary") or {}
            st = bs.get("short_term_gain_loss")
            lt = bs.get("long_term_gain_loss")
            if st is not None: cap_gain += float(st); has_any = True
            if lt is not None: cap_gain += float(lt); has_any = True

        # Fed withheld from trades
        for trade in ej.get("brokerage_1099_trades", []):
            fw = trade.get("federal_income_tax_withheld")
            if fw is not None:
                b_withheld += float(fw)
                has_any = True
                if name not in b1099_sources:
                    b1099_sources.append(name)

        # Form 1098
        for f in ej.get("form_1098", []):
            vm = f.get("mortgage_interest_received")
            vr = f.get("real_estate_taxes")
            if vm is not None: mortgage_int    += float(vm); has_any = True
            if vr is not None: real_estate_tax += float(vr); has_any = True
            if vm is not None or vr is not None:
                if name not in f1098_sources:
                    f1098_sources.append(name)

    if not has_any:
        return {}

    total_withheld = w2_withheld + b_withheld

    lines = [
        {
            "key":   "line_1a",
            "label": "1a — W-2 wages, salaries, tips",
            "value": w2_wages if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key":   "line_1z",
            "label": "1z — Total wages (same as 1a if no adjustments)",
            "value": w2_wages if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key":   "line_2b",
            "label": "2b — Taxable interest",
            "value": interest if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key":   "line_3a",
            "label": "3a — Qualified dividends",
            "value": qual_dividends if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key":   "line_3b",
            "label": "3b — Ordinary dividends",
            "value": ord_dividends if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key":   "line_7",
            "label": "7 — Capital gain or (loss)",
            "value": cap_gain if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key":   "line_25a",
            "label": "25a — Federal income tax withheld (W-2)",
            "value": w2_withheld if w2_sources else None,
            "sources": w2_sources,
            "sched": None,
        },
        {
            "key":   "line_25b",
            "label": "25b — Federal income tax withheld (1099)",
            "value": b_withheld if b1099_sources else None,
            "sources": b1099_sources,
            "sched": None,
        },
        {
            "key":   "line_25d",
            "label": "25d — Total federal income tax withheld",
            "value": total_withheld if (w2_sources or b1099_sources) else None,
            "sources": w2_sources + [s for s in b1099_sources if s not in w2_sources],
            "sched": None,
        },
        {
            "key":   "scha_8a",
            "label": "Sched A 8a — Home mortgage interest",
            "value": mortgage_int if f1098_sources else None,
            "sources": f1098_sources,
            "sched": "A",
        },
        {
            "key":   "scha_5b",
            "label": "Sched A 5b — Real estate taxes",
            "value": real_estate_tax if f1098_sources else None,
            "sources": f1098_sources,
            "sched": "A",
        },
    ]

    return {"lines": lines}


def fill_1040_pdf(data: dict, template_path: str) -> bytes:
    """
    Overlay computed Form 1040 values onto the flat PDF template.
    Returns PDF bytes. Falls back to blank template on any error.
    """
    try:
        return _do_fill(data, template_path)
    except Exception:
        with open(template_path, "rb") as fh:
            return fh.read()


def _do_fill(data: dict, template_path: str) -> bytes:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import letter
    import pypdf

    lines = (data or {}).get("lines", [])

    # Group values by page index
    page_values: dict[int, list[tuple[float, float, str]]] = {}
    for line in lines:
        key   = line["key"]
        value = line["value"]
        if value is None or key not in _FIELD_COORDS:
            continue
        pg, rx, ry = _FIELD_COORDS[key]
        text = _fmt(value)
        page_values.setdefault(pg, []).append((rx, ry, text))

    # Open the template to find page count and sizes
    reader = pypdf.PdfReader(template_path)
    num_pages = len(reader.pages)

    # Build one overlay PDF per page that needs values, blank for others
    writer = pypdf.PdfWriter()

    for pg_idx in range(num_pages):
        template_page = reader.pages[pg_idx]
        mb = template_page.mediabox
        pw = float(mb.width)
        ph = float(mb.height)

        entries = page_values.get(pg_idx, [])
        if entries:
            overlay_buf = io.BytesIO()
            c = rl_canvas.Canvas(overlay_buf, pagesize=(pw, ph))
            c.setFont("Helvetica", 9)
            for rx, ry, text in entries:
                # Right-align: measure text width and shift left
                text_w = c.stringWidth(text, "Helvetica", 9)
                x = rx - text_w
                c.drawString(x, ry, text)
            c.save()
            overlay_buf.seek(0)

            overlay_reader = pypdf.PdfReader(overlay_buf)
            overlay_page   = overlay_reader.pages[0]
            template_page.merge_page(overlay_page)

        writer.add_page(template_page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
