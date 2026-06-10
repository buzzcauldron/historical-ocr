"""Printed page text extraction.

Vendored from research-party ``cli/bib_pdf_ocr.py`` (_extract_page_text*).
"""

from __future__ import annotations

from pathlib import Path

_MIN_CHARS_FOR_OCR_FALLBACK = 80


def ocr_image(image: Path, *, lang: str = "lat+frk+eng") -> str:
    import pytesseract
    from PIL import Image

    with Image.open(image) as im:
        return pytesseract.image_to_string(im, lang=lang).strip()


def extract_pdf_page_text(
    pdf_path: Path,
    page_idx: int,
    *,
    lang: str = "lat+frk+eng",
    ocr_dpi: int = 200,
) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    try:
        text = (reader.pages[page_idx].extract_text() or "").strip()
    except Exception:
        text = ""

    if len(text) >= _MIN_CHARS_FOR_OCR_FALLBACK:
        return text

    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(
            str(pdf_path),
            first_page=page_idx + 1,
            last_page=page_idx + 1,
            dpi=ocr_dpi,
        )
        if images:
            return pytesseract.image_to_string(images[0], lang=lang, config="--psm 6").strip()
    except Exception:
        pass
    return text
