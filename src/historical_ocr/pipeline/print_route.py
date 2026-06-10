"""Printed-text OCR using vendored page extractors."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.config import JobPaths, Settings
from historical_ocr.lib.print_ocr import extract_pdf_page_text, ocr_image
from historical_ocr.models.manifest import JobManifest, PageRecord


def ocr_pages(
    pages: list[PageRecord],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
    *,
    source_pdf: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    job.ensure()

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    for page in pages:
        if page.route != "print":
            continue

        image = job.root / page.image_path
        out_txt = job.ocr / f"{page.page_id}.txt"
        _log(f"print-ocr: {page.page_id}")

        try:
            if source_pdf and source_pdf.is_file():
                try:
                    idx = int(page.page_id.rsplit("_p", 1)[-1])
                except ValueError:
                    idx = 0
                text = extract_pdf_page_text(
                    source_pdf,
                    idx,
                    lang=settings.tesseract_lang,
                )
            else:
                text = ocr_image(image, lang=settings.tesseract_lang)
        except Exception as e:
            page.status = "error"
            page.errors.append(str(e))
            continue

        out_txt.write_text(text + "\n", encoding="utf-8")
        page.ocr_text_path = str(out_txt.relative_to(job.root))
        page.status = "ok"
