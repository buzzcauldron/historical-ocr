"""Pre-OCR text-section filtering for overlaid OCR regions."""

from __future__ import annotations

import statistics
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from historical_ocr.config import Settings
from historical_ocr.lib.region_ocr import RegionBox


class SectionKind(Enum):
    prose = "prose"
    list = "list"
    header = "header"
    advertisement = "advertisement"
    illustration = "illustration"
    handwriting = "handwriting"
    other = "other"


_INK_THRESHOLD = 175
_WIDE_ROW_FRAC = 0.45
_ILLUSTRATION_WIDE_ROW_FRAC = 0.30
_ILLUSTRATION_FILL_FRAC = 0.20
_AD_HEIGHT_FRAC = 0.40
_HEADER_HEIGHT_FRAC = 0.12


def _to_gray_array(gray: Any) -> np.ndarray:
    if hasattr(gray, "convert"):
        gray = np.asarray(gray.convert("L"), dtype=np.uint8)
    else:
        gray = np.asarray(gray, dtype=np.uint8)
    if gray.ndim != 2:
        raise ValueError("Expected 2D grayscale data")
    return gray


def _ink_mask(gray: np.ndarray) -> np.ndarray:
    return gray < _INK_THRESHOLD


def _longest_ink_run(row: np.ndarray) -> int:
    best = 0
    run = 0
    for pixel in row:
        if pixel:
            run += 1
            if run > best:
                best = run
        else:
            run = 0
    return best


def _row_run_fractions(ink: np.ndarray) -> list[float]:
    h, w = ink.shape
    fractions: list[float] = []
    for y in range(h):
        if not ink[y].any():
            continue
        fractions.append(_longest_ink_run(ink[y]) / float(w))
    return fractions


def _blob_fill_fraction(ink: np.ndarray) -> float:
    total = ink.size
    if total == 0:
        return 0.0
    return float(ink.sum()) / total


def _row_segments(ink: np.ndarray) -> tuple[list[int], list[int]]:
    bands: list[int] = []
    gaps: list[int] = []
    h = ink.shape[0]
    in_band = False
    band_start = 0
    gap_start = 0
    for y in range(h):
        if ink[y].any():
            if not in_band:
                in_band = True
                band_start = y
            if gap_start is not None and gap_start < y:
                gap_len = y - gap_start
                if gap_len:
                    gaps.append(gap_len)
                gap_start = h
        else:
            if in_band:
                bands.append(y - band_start)
                in_band = False
                gap_start = y
    if in_band:
        bands.append(h - band_start)
    return bands, gaps


def _regular_line_rhythm(bands: list[int], gaps: list[int]) -> bool:
    if len(bands) < 3 or len(gaps) < 2:
        return False
    mean_gap = statistics.mean(gaps)
    if mean_gap < 3.0:
        return False
    if statistics.pstdev(gaps) / mean_gap > 0.40:
        return False
    return True


def classify_ink_section(crop_gray: Any, *, page_height: int) -> SectionKind:
    gray = _to_gray_array(crop_gray)
    h, w = gray.shape
    if h == 0 or w == 0:
        return SectionKind.other

    ink = _ink_mask(gray)
    if not ink.any():
        return SectionKind.other

    run_fracs = _row_run_fractions(ink)
    if not run_fracs:
        return SectionKind.other

    wide_row_frac = sum(1 for frac in run_fracs if frac >= _WIDE_ROW_FRAC) / len(run_fracs)
    avg_run_frac = statistics.mean(run_fracs)
    blob_frac = _blob_fill_fraction(ink)
    bands, gaps = _row_segments(ink)
    has_rhythm = _regular_line_rhythm(bands, gaps)
    mean_band = statistics.mean(bands) if bands else 0.0

    if h <= page_height * _HEADER_HEIGHT_FRAC and len(bands) <= 5:
        return SectionKind.header

    if h <= page_height * _AD_HEIGHT_FRAC and avg_run_frac < 0.60 and len(bands) >= 2:
        return SectionKind.advertisement

    if has_rhythm and avg_run_frac >= 0.50 and mean_band >= 3.0:
        return SectionKind.prose

    if has_rhythm and avg_run_frac < 0.60 and len(bands) >= 3:
        return SectionKind.list

    if not has_rhythm and (wide_row_frac >= 0.65 or blob_frac >= 0.30):
        return SectionKind.illustration

    if not has_rhythm and blob_frac >= 0.08 and avg_run_frac < 0.40:
        return SectionKind.handwriting

    return SectionKind.other


def filter_text_regions(
    image: Path,
    regions: list[RegionBox],
    settings: Settings | None = None,
) -> tuple[list[RegionBox], list[tuple[RegionBox, SectionKind]]]:
    settings = settings or Settings()
    if not getattr(settings, "text_slice_only", False):
        return regions, []

    include_ad = getattr(settings, "text_slice_include_ads", False)
    include_figures = getattr(settings, "text_slice_include_figures", False)
    keep_kinds = {SectionKind.prose, SectionKind.list}
    if include_ad:
        keep_kinds.add(SectionKind.advertisement)
        keep_kinds.add(SectionKind.header)
    if include_figures:
        keep_kinds.add(SectionKind.illustration)

    kept: list[RegionBox] = []
    skipped: list[tuple[RegionBox, SectionKind]] = []
    with Image.open(image) as im:
        gray_page = im.convert("L")
        for region in regions:
            left = int(region.left)
            top = int(region.top)
            right = min(gray_page.width, left + int(region.width))
            bottom = min(gray_page.height, top + int(region.height))
            crop = gray_page.crop((left, top, right, bottom))
            kind = classify_ink_section(crop, page_height=gray_page.height)
            if kind in keep_kinds:
                kept.append(region)
            else:
                skipped.append((region, kind))

    return kept, skipped


def summarize_skipped(skipped: list[tuple[RegionBox, SectionKind]]) -> str:
    counts = Counter(kind.value for _, kind in skipped)
    if not counts:
        return ""
    parts = [f"{count} {kind}" for kind, count in counts.items()]
    return ", ".join(parts)
