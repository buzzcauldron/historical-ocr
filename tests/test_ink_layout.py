"""Ink layout detection and heatmap."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from historical_ocr.lib.glyph_heatmap import render_page_review_heatmap
from historical_ocr.lib.ink_layout import (
    InkLayout,
    InkSection,
    analyze_ink_layout,
    column_count_from_ink_zones,
    detect_column_bounds,
    detect_horizontal_bands,
    has_multiple_columns,
    render_ink_layout_heatmap,
)


def test_detect_horizontal_bands() -> None:
    gray = np.full((400, 200), 255, dtype=np.uint8)
    gray[50:120, 20:180] = 30
    gray[200:320, 20:180] = 30
    bands = detect_horizontal_bands(gray, 0, 200, min_gap_px=10, min_band_px=30)
    assert len(bands) == 2


def test_analyze_ink_layout_three_columns() -> None:
    gray = np.full((800, 900), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:700, x0:x1] = 30
    layout = analyze_ink_layout(gray, page_width=900, page_height=800, min_gutter_px=10)
    assert len(layout.columns) == 3
    assert len(layout.sections) >= 3


def test_detect_columns_ignores_full_width_header() -> None:
    gray = np.full((800, 900), 255, dtype=np.uint8)
    gray[20:80, :] = 30
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:700, x0:x1] = 30
    bounds = detect_column_bounds(gray, min_gutter_px=10)
    assert len(bounds) == 3
    assert has_multiple_columns(gray, min_gutter_px=10)
    assert column_count_from_ink_zones(gray, min_gutter_px=10) == 3


def test_render_ink_layout_heatmap(tmp_path) -> None:
    image = tmp_path / "page.jpg"
    Image.new("RGB", (300, 400), "white").save(image)
    layout = InkLayout(
        page_width=300,
        page_height=400,
        columns=(),
        sections=(
            InkSection(section_id=1, left=20, top=50, width=80, height=120, column_index=0),
        ),
    )
    out = tmp_path / "ink.png"
    assert render_ink_layout_heatmap(image, out, layout) is True
    assert out.is_file()


def test_review_heatmap_layers_ink_first(tmp_path) -> None:
    np = pytest.importorskip("numpy")
    image = tmp_path / "page.jpg"
    arr = np.full((200, 300, 3), 255, dtype=np.uint8)
    arr[60:140, 40:120] = 30
    Image.fromarray(arr).save(image)

    from historical_ocr.lib.ink_layout import analyze_ink_layout_image

    ink = analyze_ink_layout_image(image, min_gutter_px=8)
    assert ink is not None

    out = tmp_path / "review.png"
    assert render_page_review_heatmap(image, out, ink_layout=ink) is True
    assert out.is_file()
