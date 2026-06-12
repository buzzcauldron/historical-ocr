"""Normalize sources to per-page images."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

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
        optimize=settings.jpeg_optimize,
        deskew=settings.deskew_enabled,
        deskew_max_angle=settings.deskew_max_angle,
        deskew_min_angle=settings.deskew_min_angle,
    )
    if meta.output.resolve() != src.resolve() and src.parent == dest.parent:
        src.unlink(missing_ok=True)
    return meta.output


def prepare_pages(
    sources: list[Path],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
    log_fn: Callable[[str], None] | None = None,
) -> list[PageRecord]:
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    job.ensure()
    pages: list[PageRecord] = []

    for src in sources:
        suffix = src.suffix.lower()
        if suffix == _PDF_SUFFIX:
            _log(f"prepare: rendering {src.name} → pages/")
            rendered = extract_pdf_pages(
                src,
                job.pages,
                dpi=settings.pdf_dpi,
                jpeg_quality=settings.jpeg_quality,
            )
            _log(f"prepare: {src.name} → {len(rendered)} page image(s)")
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
            _log(f"prepare: normalizing {src.name}")
            dest = job.pages / f"{src.stem}.jpg"
            normalized = _normalize_into_pages(src, dest, settings)
            pages.append(
                PageRecord(
                    page_id=src.stem,
                    image_path=str(normalized.relative_to(job.root)),
                ),
            )
        else:
            raise ValueError(f"Unsupported source: {src}")

    _log(f"prepare: {len(pages)} page(s) ready")
    manifest.pages = pages
    return pages
