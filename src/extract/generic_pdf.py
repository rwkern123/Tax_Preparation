from __future__ import annotations

from pathlib import Path
from typing import List

from src.config import MIN_TEXT_LENGTH_FOR_OCR_SKIP


def extract_pdf_text(path: Path) -> str:
    text_parts: List[str] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
    except Exception:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        except Exception:
            return ""
    return "\n".join(text_parts).strip()


def ocr_image_or_pdf(path: Path) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return ""

    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        try:
            return pytesseract.image_to_string(Image.open(path))
        except Exception:
            return ""

    try:
        from pdf2image import convert_from_path  # type: ignore

        pages = convert_from_path(str(path))
        return "\n".join(pytesseract.image_to_string(p) for p in pages)
    except Exception:
        return ""


def get_document_text(path: Path, enable_ocr: bool) -> tuple[str, list[str]]:
    notes: list[str] = []
    text = ""
    if path.suffix.lower() == ".pdf":
        text = extract_pdf_text(path)
        if text:
            notes.append("embedded_text_extracted")
    if enable_ocr and len(text) < MIN_TEXT_LENGTH_FOR_OCR_SKIP:
        ocr_text = ocr_image_or_pdf(path)
        if ocr_text:
            text = f"{text}\n{ocr_text}".strip()
            notes.append("ocr_applied")
    return text, notes
