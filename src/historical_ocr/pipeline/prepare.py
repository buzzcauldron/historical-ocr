"""Normalize sources to per-page images."""

from __future__ import annotations

import shutil
from pathlib import Path

from historical_ocr.config import JobPaths, Settings
from historical_ocr.lib.pdf_pages import extract_pdf_pages
from historical_ocr.models.manifest import JobManifest, PageRecord

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
_PDF_SUFFIX = ".pdf"


def _page_id(stem: str, index: int) -> str:
    return f"{stem}_p{index:04d}"


def prepare_pages(
    sources: list[Path],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
) -> list[PageRecord]:
    job.ensure()
    pages: list[PageRecord] = []

    for src in sources:
        suffix = src.suffix.lower()
        if suffix == _PDF_SUFFIX:
            rendered = extract_pdf_pages(src, job.pages, dpi=settings.pdf_dpi)
            for i, img in enumerate(rendered):
                pages.append(
                    PageRecord(
                        page_id=_page_id(src.stem, i),
                        image_path=str(img.relative_to(job.root)),
                    ),
                )
        elif suffix in _IMAGE_SUFFIXES:
            dest = job.pages / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            pages.append(
                PageRecord(
                    page_id=_page_id(dest.stem, 0),
                    image_path=str(dest.relative_to(job.root)),
                ),
            )
        else:
            raise ValueError(f"Unsupported source: {src}")

    manifest.pages = pages
    return pages
