"""Multi-column newspaper detection and merge."""

from __future__ import annotations

import numpy as np

from historical_ocr.lib.column_ocr import detect_column_bounds
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.lib.region_ocr import RegionBox, merge_region_results


def test_detect_three_columns() -> None:
    gray = np.full((1000, 900), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:900, x0:x1] = 30
    bounds = detect_column_bounds(gray, min_gutter_px=10)
    assert len(bounds) == 3


def test_detect_single_column_fallback() -> None:
    gray = np.full((400, 600), 255, dtype=np.uint8)
    gray[50:350, 80:520] = 20
    bounds = detect_column_bounds(gray)
    assert bounds == [(0, 600)]


def test_merge_column_lines_reading_order() -> None:
    left = LayoutOcrResult(
        lines=[OcrLine(1, "alpha", 10, 100, 80, 12, 90.0)],
        page_width=300,
        page_height=400,
        full_text="alpha",
    )
    right = LayoutOcrResult(
        lines=[OcrLine(1, "beta", 10, 50, 80, 12, 90.0)],
        page_width=300,
        page_height=400,
        full_text="beta",
    )
    merged = merge_region_results(
        [
            (RegionBox(left=0, top=0, width=300, height=400, sort_col=0), left),
            (RegionBox(left=300, top=0, width=300, height=400, sort_col=1), right),
        ],
        page_width=600,
        page_height=400,
    )
    assert [l.text for l in merged.lines] == ["alpha", "beta"]
    assert merged.lines[0].left == 10
    assert merged.lines[1].left == 310


def test_twentieth_century_enables_column_ocr() -> None:
    from historical_ocr.document_types.print_types import load_print_doc_type

    spec = load_print_doc_type("twentieth_century")
    assert spec.tei_section_ocr is True
    assert spec.column_ocr is True
    assert spec.column_ocr_psm == 6
