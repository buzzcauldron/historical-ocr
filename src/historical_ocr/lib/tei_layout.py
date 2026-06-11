"""TEI P5 helpers for sectioned print layout."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from historical_ocr.lib.layout_export import TEI_NS
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, TeiSection

_T = f"{{{TEI_NS}}}"
_XML = "{http://www.w3.org/XML/1998/namespace}id"


def _section_coord(section: TeiSection) -> str:
    return f"{section.left},{section.top},{section.width},{section.height}"


def _append_line(parent: ET.Element, page_id: str, line: OcrLine) -> None:
    lb_id = f"lb_{page_id}_{line.line_num}"
    lb = ET.SubElement(
        parent,
        f"{_T}lb",
        {
            "n": str(line.line_num),
            _XML: lb_id,
            "rend": "line",
            "coord": f"{line.left},{line.top},{line.width},{line.height}",
        },
    )
    lb.tail = line.text


def _lines_for_section(lines: list[OcrLine], section_id: int) -> list[OcrLine]:
    tagged = [ln for ln in lines if ln.section_id == section_id and ln.text.strip()]
    if tagged:
        return tagged
    return []


def append_sectioned_page_content(
    page_div: ET.Element,
    page_id: str,
    layout: LayoutOcrResult,
) -> None:
    """Emit nested ``div`` elements (column → section type) with line breaks."""
    if not layout.sections:
        p = ET.SubElement(page_div, f"{_T}p")
        for line in layout.lines:
            if line.text.strip():
                _append_line(p, page_id, line)
        return

    by_column: dict[int, list[TeiSection]] = {}
    for section in layout.sections:
        by_column.setdefault(section.column_index, []).append(section)

    for col_idx in sorted(by_column):
        col_sections = sorted(by_column[col_idx], key=lambda s: s.top)
        col_div = ET.SubElement(page_div, f"{_T}div", type="column", n=str(col_idx + 1))

        for section in col_sections:
            sect_div = ET.SubElement(
                col_div,
                f"{_T}div",
                type=section.section_type,
                n=str(section.section_id),
            )
            sect_div.set("coord", _section_coord(section))
            p = ET.SubElement(sect_div, f"{_T}p")
            for line in _lines_for_section(layout.lines, section.section_id):
                _append_line(p, page_id, line)


def append_sectioned_facsimile_zones(
    surface: ET.Element,
    page_id: str,
    layout: LayoutOcrResult,
) -> None:
    for section in layout.sections:
        ET.SubElement(
            surface,
            f"{_T}zone",
            {
                "rendition": section.section_type,
                "ulx": str(section.left),
                "uly": str(section.top),
                "lrx": str(section.left + section.width),
                "lry": str(section.top + section.height),
                "corresp": f"#sect_{page_id}_{section.section_id}",
            },
        )

    for line in layout.lines:
        if not line.text.strip():
            continue
        ET.SubElement(
            surface,
            f"{_T}zone",
            {
                "rendition": "textline",
                "ulx": str(line.left),
                "uly": str(line.top),
                "lrx": str(line.left + line.width),
                "lry": str(line.top + line.height),
                "corresp": f"#lb_{page_id}_{line.line_num}",
            },
        )
