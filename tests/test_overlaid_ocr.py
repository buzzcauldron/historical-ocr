"""Ink-zone overlaid OCR."""

from __future__ import annotations

import numpy as np

from historical_ocr.lib.ink_layout import InkColumn, InkLayout, InkSection, analyze_ink_layout
from historical_ocr.lib.overlaid_ocr import regions_from_ink_layout


def test_regions_from_sections() -> None:
    layout = InkLayout(
        page_width=900,
        page_height=800,
        columns=(InkColumn(0, 0, 900),),
        sections=(
            InkSection(1, 0, 50, 450, 300, 0),
            InkSection(2, 450, 80, 450, 280, 1),
        ),
    )
    regions = regions_from_ink_layout(layout, use_sections=True)
    assert len(regions) == 2
    assert regions[0].left == 0 and regions[1].left == 450


def test_regions_prefer_columns_when_multi_column() -> None:
    layout = InkLayout(
        page_width=900,
        page_height=800,
        columns=(InkColumn(0, 0, 450), InkColumn(1, 450, 450)),
        sections=(
            InkSection(1, 0, 50, 450, 300, 0),
            InkSection(2, 450, 80, 450, 280, 1),
        ),
    )
    regions = regions_from_ink_layout(layout, use_sections=True)
    assert len(regions) == 2
    assert regions[0].height == 800 and regions[0].top == 0


def test_regions_from_columns_when_single_section() -> None:
    layout = InkLayout(
        page_width=900,
        page_height=800,
        columns=(
            InkColumn(0, 40, 200),
            InkColumn(1, 340, 200),
            InkColumn(2, 640, 200),
        ),
        sections=(
            InkSection(1, 0, 0, 900, 800, 0),
        ),
    )
    regions = regions_from_ink_layout(layout, use_sections=False)
    assert len(regions) == 3


def test_analyze_layout_produces_overlay_regions() -> None:
    gray = np.full((800, 900), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:700, x0:x1] = 30
    layout = analyze_ink_layout(gray, page_width=900, page_height=800, min_gutter_px=10)
    regions = regions_from_ink_layout(layout)
    assert len(regions) >= 2
