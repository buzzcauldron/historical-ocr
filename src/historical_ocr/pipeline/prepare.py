"""Normalize sources to per-page images."""

from __future__ import annotations

import shutil
from pathlib import Path

from historical_ocr.config import JobPaths, Settings
from historical_ocr.image_tools.convert import normalize_page_image
from historical_ocr.lib.pdf_pages import extract_pdf_pages
from historical_ocr.models.manifest import JobManifest, PageRecord

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
_PDF_SUFFIX = ".pdf"


def _page_id(stem: str, index: int) -> str:
    return f"{stem}_p{index:04d}"


def _normalize_into_pages(src: Path, dest: Path, settings: Settings) -> Path:
    meta = normalize_page_image(
        src,
        dest,
        max_width=settings.max_image_width,
        max_height=settings.max_image_height,
        max_pixels=settings.max_image_pixels,
        quality=settings.jpeg_quality,
    )
    if meta.output.resolve() != src.resolve() and src.parent == dest.parent:
        src.unlink(missing_ok=True)
    return meta.output


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
            rendered = extract_pdf_pages(
                src,
                job.pages,
                dpi=settings.pdf_dpi,
                jpeg_quality=settings.jpeg_quality,
            )
            for i, img in enumerate(rendered):
                normalized = _normalize_into_pages(
                    img,
                    job.pages / f"{img.stem}.jpg",
                    settings,
                )
                pages.append(
                    PageRecord(
                        page_id=_page_id(src.stem, i),
                        image_path=str(normalized.relative_to(job.root)),
                    ),
                )
        elif suffix in _IMAGE_SUFFIXES:
            dest = job.pages / f"{src.stem}.jpg"
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            normalized = _normalize_into_pages(dest, dest, settings)
            pages.append(
                PageRecord(
                    page_id=src.stem,
                    image_path=str(normalized.relative_to(job.root)),
                ),
            )
        else:
            raise ValueError(f"Unsupported source: {src}")

    manifest.pages = pages
    return pages
