"""Citation-density heuristics for PDF OCR targeting.

Adapted from buzzcauldron/bib-ocr ``bib_ocr/density.py`` (MIT).
Targets Tesseract on pages/regions where references or sparse text layers appear.
"""

from __future__ import annotations

import re
from pathlib import Path

from historical_ocr.lib.bib_section_heads import SECTION_HEADER_DENSITY_RE

_CITATION_RE = re.compile(
    r"(?:"
    r"\b10\.[0-9]{4,}/[^\s\"'<>,;)\]\s]{3,}"
    r"|(?<!\w)\[\s*\d{1,3}\s*\]"
    r"|\b[A-Z][a-z]{1,20}"
    r"(?:\s+(?:et\s+al\.?|and|&)\s+[A-Z][a-z]{1,20})?"
    r"\s*[\(\[]\s*\d{4}\s*[\)\]]"
    r"|[†‡§¶]"
    r")",
    re.UNICODE,
)


def page_density(pdf_path: str | Path, bands: int = 10):
    """Return float32 array (n_pages, bands) of citation-marker counts per vertical band."""
    try:
        import fitz
        import numpy as np
    except ImportError as exc:
        raise ImportError("page_density requires pymupdf and numpy: pip install -e '.[pdf]'") from exc

    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    n = len(doc)
    arr = np.zeros((n, bands), dtype=np.float32)

    for i, page in enumerate(doc):
        page_h = page.rect.height or 1.0
        for block in page.get_text("blocks"):
            if block[6] != 0:
                continue
            text = block[4]
            y_center = (block[1] + block[3]) / 2.0
            band_idx = min(int(y_center / page_h * bands), bands - 1)
            arr[i, band_idx] += len(_CITATION_RE.findall(text))

        page_text = page.get_text()
        if SECTION_HEADER_DENSITY_RE.search(page_text):
            arr[i, :] += 3.0

    doc.close()
    return arr


def target_pages(
    density,
    *,
    threshold_fraction: float = 0.10,
    min_signal: float = 1.0,
    margin: int = 1,
) -> list[int]:
    page_scores = density.sum(axis=1)
    threshold = max(min_signal, float(page_scores.max()) * threshold_fraction)
    hot: set[int] = set()
    for i, s in enumerate(page_scores):
        if s >= threshold:
            for offset in range(-margin, margin + 1):
                j = i + offset
                if 0 <= j < len(page_scores):
                    hot.add(j)
    return sorted(hot)


def ref_section_start(density) -> int:
    page_scores = density.sum(axis=1)
    if page_scores.max() == 0:
        return max(0, len(page_scores) - 4)

    threshold = float(page_scores.max()) * 0.15
    hot_pages = [i for i, s in enumerate(page_scores) if s >= threshold]
    if not hot_pages:
        return max(0, len(page_scores) - 4)

    last = hot_pages[-1]
    start = last
    for p in reversed(hot_pages):
        if last - p <= 3:
            start = p
            last = p
        else:
            break
    return start


def pages_needing_ocr(
    pdf_path: str | Path,
    *,
    min_embedded_chars: int = 80,
) -> set[int] | None:
    """Pages with sparse embedded text and/or citation-density signal.

    Returns ``None`` when pymupdf is unavailable (caller should OCR all pages).
    """
    try:
        import fitz
    except ImportError:
        return None

    pdf_path = Path(pdf_path)
    sparse: set[int] = set()
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc):
        text = (page.get_text() or "").strip()
        if len(text) < min_embedded_chars:
            sparse.add(i)
    doc.close()

    try:
        density = page_density(pdf_path)
        hot = set(target_pages(density))
        tail = set(range(ref_section_start(density), len(density)))
        return sparse | hot | tail
    except Exception:
        return sparse or None
