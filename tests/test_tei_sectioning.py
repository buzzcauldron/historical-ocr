"""TEI section detection and sectioned OCR."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np

from historical_ocr.document_types.print_types import load_print_doc_type
from historical_ocr.lib.layout_export import lines_to_tei
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, TeiSection
from historical_ocr.lib.ink_layout import detect_horizontal_bands
from historical_ocr.lib.tei_sectioning import (
    classify_section,
    detect_page_sections,
    refine_section_types,
)


def test_detect_horizontal_bands() -> None:
    gray = np.full((400, 200), 255, dtype=np.uint8)
    gray[50:120, 20:180] = 30
    gray[200:320, 20:180] = 30
    bands = detect_horizontal_bands(gray, 0, 200, min_gap_px=10, min_band_px=30)
    assert len(bands) == 2


def test_detect_page_sections_three_columns() -> None:
    gray = np.full((800, 900), 255, dtype=np.uint8)
    for x0, x1 in ((40, 240), (340, 540), (640, 840)):
        gray[100:700, x0:x1] = 30
    sections = detect_page_sections(gray, min_gutter_px=10)
    assert len(sections) >= 3
    columns = {s.column_index for s in sections}
    assert len(columns) == 3


def test_classify_list_section() -> None:
    section = TeiSection(1, "section", 0, 400, 200, 200, 1)
    lines = [
        OcrLine(1, "1. Flash lights", 10, 410, 100, 12, 90.0, section_id=1),
        OcrLine(2, "2. Soap and toilet paper", 10, 430, 150, 12, 90.0, section_id=1),
        OcrLine(3, "3. Matches", 10, 450, 80, 12, 90.0, section_id=1),
    ]
    assert classify_section(lines, section, page_height=800) == "list"


def test_classify_advertisement() -> None:
    section = TeiSection(2, "section", 600, 650, 200, 120, 2)
    lines = [
        OcrLine(1, "NOBBY'S MEN'S SHOP", 610, 660, 180, 14, 88.0, section_id=2),
        OcrLine(2, "SPRINGFIELD AVE.", 610, 680, 160, 14, 88.0, section_id=2),
    ]
    assert classify_section(lines, section, page_height=800) == "advertisement"


def test_refine_section_types() -> None:
    sections = [
        TeiSection(1, "section", 0, 400, 200, 180, 0),
        TeiSection(2, "section", 600, 650, 200, 120, 2),
    ]
    lines = [
        OcrLine(1, "1. Canned vegetables", 10, 410, 120, 12, 90.0, section_id=1),
        OcrLine(2, "2. Dried beans", 10, 430, 100, 12, 90.0, section_id=1),
        OcrLine(3, "BARGAIN FAIR FURNITURE CO.", 610, 660, 180, 14, 88.0, section_id=2),
    ]
    refined = refine_section_types(sections, lines, page_height=800)
    assert refined[0].section_type == "list"
    assert refined[1].section_type == "advertisement"


def test_lines_to_tei_nested_divs(tmp_path) -> None:
    layout = LayoutOcrResult(
        lines=[
            OcrLine(1, "1. Canned vegetables", 10, 410, 120, 12, 90.0, section_id=1),
            OcrLine(2, "NOBBY'S MEN'S SHOP", 610, 660, 180, 14, 88.0, section_id=2),
        ],
        page_width=900,
        page_height=800,
        full_text="1. Canned vegetables\nNOBBY'S MEN'S SHOP",
        sections=(
            TeiSection(1, "list", 0, 400, 200, 180, 0),
            TeiSection(2, "advertisement", 600, 650, 200, 120, 2),
        ),
    )
    tei_path = tmp_path / "page.tei.xml"
    lines_to_tei("p1", layout, tei_path)
    xml = tei_path.read_text(encoding="utf-8")
    root = ET.fromstring(xml)
    assert root.find(".//{*}div[@type='column']") is not None
    assert root.find(".//{*}div[@type='list']") is not None
    assert root.find(".//{*}div[@type='advertisement']") is not None
    assert "Canned vegetables" in xml


def test_twentieth_century_enables_tei_section_ocr() -> None:
    spec = load_print_doc_type("twentieth_century")
    assert spec.tei_section_ocr is True
    assert spec.tei_section_psm == 6
