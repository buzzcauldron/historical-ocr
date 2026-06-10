"""Layout export: TEI, PAGE-XML, and clean TXT."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from historical_ocr.lib.layout_export import (
    lines_to_clean_txt,
    lines_to_pagexml,
    lines_to_tei,
    text_to_layout_result,
)
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


def test_lines_to_clean_txt() -> None:
    lines = [
        OcrLine(1, "Hello", 0, 0, 10, 10, 90.0),
        OcrLine(2, "World", 0, 20, 10, 10, 90.0),
    ]
    assert lines_to_clean_txt(lines) == "Hello\nWorld"


def test_tei_and_pagexml_preserve_layout(tmp_path: Path) -> None:
    layout = LayoutOcrResult(
        lines=[
            OcrLine(1, "First line", 10, 20, 200, 18, 95.0),
            OcrLine(2, "Second line", 10, 50, 220, 18, 92.0),
        ],
        page_width=800,
        page_height=600,
        full_text="First line\nSecond line",
    )
    tei_path = tmp_path / "page.tei.xml"
    page_path = tmp_path / "page.pagexml"
    lines_to_tei("p1", layout, tei_path)
    lines_to_pagexml("p1", "p1.jpg", layout, page_path)

    tei = tei_path.read_text(encoding="utf-8")
    assert "First line" in tei
    assert 'coord="10,20,200,18"' in tei
    assert "facsimile" in tei

    page_xml = page_path.read_text(encoding="utf-8")
    root = ET.fromstring(page_xml)
    assert "TextLine" in page_xml
    assert root.find(".//{*}Unicode") is not None


def test_text_to_layout_result_fallback() -> None:
    layout = text_to_layout_result("alpha\nbeta")
    assert len(layout.lines) == 2
    assert layout.lines[0].text == "alpha"
