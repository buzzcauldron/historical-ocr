"""Tests for pre-OCR text-section filtering."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from historical_ocr.lib.region_ocr import RegionBox
from historical_ocr.lib.text_section_filter import (
    SectionKind,
    classify_ink_section,
    filter_text_regions,
    summarize_skipped,
)


def _save_gray(array: np.ndarray, path: Path) -> None:
    Image.fromarray(array, mode="L").save(path)


def test_classify_prose_region() -> None:
    gray = np.full((120, 240), 255, dtype=np.uint8)
    for y in range(10, 110, 12):
        gray[y : y + 3, 20:220] = 30
    kind = classify_ink_section(gray, page_height=120)
    assert kind == SectionKind.prose


def test_classify_illustration_region() -> None:
    gray = np.full((120, 240), 255, dtype=np.uint8)
    gray[10:110, 20:220] = 30
    kind = classify_ink_section(gray, page_height=120)
    assert kind == SectionKind.illustration


def test_classify_advertisement_region() -> None:
    gray = np.full((80, 240), 255, dtype=np.uint8)
    for y in range(10, 70, 12):
        gray[y : y + 2, 40:120] = 30
    kind = classify_ink_section(gray, page_height=240)
    assert kind == SectionKind.advertisement


def test_filter_text_regions_skips_non_text_when_enabled(tmp_path: Path) -> None:
    gray = np.full((120, 240), 255, dtype=np.uint8)
    gray[10:110, 20:220] = 30
    image_path = tmp_path / "illustration.png"
    _save_gray(gray, image_path)

    class DummySettings:
        text_slice_only = True
        text_slice_include_ads = False
        text_slice_include_figures = False

    regions = [RegionBox(left=0, top=0, width=240, height=120)]
    kept, skipped = filter_text_regions(image_path, regions, settings=DummySettings())
    assert len(kept) == 0
    assert len(skipped) == 1
    assert skipped[0][1] == SectionKind.illustration
    assert "illustration" in summarize_skipped(skipped)


def test_filter_text_regions_keeps_all_when_disabled(tmp_path: Path) -> None:
    gray = np.full((120, 240), 255, dtype=np.uint8)
    gray[10:110, 20:220] = 30
    image_path = tmp_path / "illustration.png"
    _save_gray(gray, image_path)

    regions = [RegionBox(left=0, top=0, width=240, height=120)]
    kept, skipped = filter_text_regions(image_path, regions, settings=None)
    assert len(kept) == 1
    assert not skipped


def test_filter_text_regions_respects_flag(tmp_path: Path) -> None:
    gray = np.full((120, 240), 255, dtype=np.uint8)
    for y in range(10, 110, 12):
        gray[y : y + 3, 20:220] = 30
    image_path = tmp_path / "prose.png"
    _save_gray(gray, image_path)

    class DummySettings:
        text_slice_only = True
        text_slice_include_ads = False
        text_slice_include_figures = False

    regions = [RegionBox(left=0, top=0, width=240, height=120)]
    kept, skipped = filter_text_regions(image_path, regions, settings=DummySettings())
    assert len(kept) == 1
    assert not skipped
