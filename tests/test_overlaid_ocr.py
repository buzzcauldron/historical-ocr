"""Ink-zone overlaid OCR."""

from __future__ import annotations

import numpy as np

from historical_ocr.lib.ink_layout import InkColumn, InkLayout, InkSection, analyze_ink_layout
from historical_ocr.lib.overlaid_ocr import expand_wide_regions, regions_from_ink_layout
from historical_ocr.lib.region_ocr import RegionBox


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


def test_regions_use_section_bands_when_fragmented_multi_column() -> None:
    """Continued-article pages: many bands per column → section crops, not full-height columns."""
    layout = InkLayout(
        page_width=900,
        page_height=800,
        columns=(
            InkColumn(0, 0, 300),
            InkColumn(1, 300, 300),
            InkColumn(2, 600, 300),
        ),
        sections=(
            InkSection(1, 0, 50, 280, 200, 0),
            InkSection(2, 0, 280, 280, 180, 0),
            InkSection(3, 0, 500, 280, 250, 0),
            InkSection(4, 300, 60, 280, 220, 1),
            InkSection(5, 300, 320, 280, 190, 1),
            InkSection(6, 300, 540, 280, 200, 1),
            InkSection(7, 600, 70, 280, 210, 2),
            InkSection(8, 600, 520, 280, 240, 2),
        ),
    )
    regions = regions_from_ink_layout(layout, use_sections=True)
    assert len(regions) == 8
    assert all(r.height < 800 for r in regions)
    assert regions[0].top == 50 and regions[0].height == 200
    assert regions[0].sort_col == 0 and regions[0].sort_band == 50


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


def test_expand_wide_regions_splits_at_gutters(tmp_path) -> None:
    """Wide section-band crops must not OCR across an internal column gutter."""
    from PIL import Image

    gray = np.full((400, 650), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540)):
        gray[80:360, x0:x1] = 30

    image = tmp_path / "wide_section.png"
    Image.fromarray(gray, mode="L").save(image)

    layout = InkLayout(
        page_width=650,
        page_height=400,
        columns=(
            InkColumn(0, 0, 200),
            InkColumn(1, 200, 200),
            InkColumn(2, 400, 250),
        ),
        sections=(
            InkSection(1, 0, 80, 580, 280, 0),
        ),
    )
    regions = [
        RegionBox(left=0, top=80, width=580, height=280, sort_col=0, sort_band=80),
    ]
    expanded = expand_wide_regions(image, regions, layout)
    assert len(expanded) == 2
    assert expanded[0].width < 580
    assert expanded[1].width < 580
    assert expanded[0].sort_subcol == expanded[0].left
    assert expanded[1].sort_subcol == expanded[1].left
    assert expanded[0].left < expanded[1].left


def test_analyze_layout_produces_overlay_regions() -> None:
    gray = np.full((800, 900), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:700, x0:x1] = 30
    layout = analyze_ink_layout(gray, page_width=900, page_height=800, min_gutter_px=10)
    regions = regions_from_ink_layout(layout)
    assert len(regions) >= 2
