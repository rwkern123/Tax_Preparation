from __future__ import annotations

from pathlib import Path
from typing import List

from src.config import MIN_TEXT_LENGTH_FOR_OCR_SKIP


def extract_pdf_text(path: Path) -> tuple[str, list[str]]:
    text_parts: List[str] = []
    notes: list[str] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        notes.append("embedded_text_extracted:pdfplumber")
    except Exception as exc_pdfplumber:
        notes.append(f"embedded_text_error:pdfplumber:{type(exc_pdfplumber).__name__}")
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            notes.append("embedded_text_extracted:pypdf")
        except Exception as exc_pypdf:
            notes.append(f"embedded_text_error:pypdf:{type(exc_pypdf).__name__}")
            return "", notes
    return "\n".join(text_parts).strip(), notes


def ocr_image_or_pdf(path: Path) -> tuple[str, list[str]]:
    notes: list[str] = []
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageOps  # type: ignore
    except Exception as exc:
        notes.append(f"ocr_unavailable:{type(exc).__name__}")
        return "", notes

    def _ocr_image(img: "Image.Image") -> str:
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img)
        return pytesseract.image_to_string(img, config="--oem 1 --psm 6")

    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        try:
            return _ocr_image(Image.open(path)), ["ocr_applied:image"]
        except Exception as exc:
            notes.append(f"ocr_error:image:{type(exc).__name__}")
            return "", notes

    try:
        from pdf2image import convert_from_path  # type: ignore

        pages = convert_from_path(str(path), dpi=300)
        notes.append(f"ocr_pdf_page_count:{len(pages)}")
        text = "\n".join(_ocr_image(p) for p in pages)
        if text.strip():
            notes.append("ocr_applied:pdf")
        return text, notes
    except Exception as exc:
        notes.append(f"ocr_error:pdf:{type(exc).__name__}")
        return "", notes


def get_document_text(path: Path, enable_ocr: bool) -> tuple[str, list[str]]:
    notes: list[str] = []
    text = ""
    if path.suffix.lower() == ".pdf":
        text, pdf_notes = extract_pdf_text(path)
        notes.extend(pdf_notes)
    if enable_ocr and len(text) < MIN_TEXT_LENGTH_FOR_OCR_SKIP:
        ocr_text, ocr_notes = ocr_image_or_pdf(path)
        notes.extend(ocr_notes)
        if ocr_text:
            text = f"{text}\n{ocr_text}".strip()
    return text, notes
