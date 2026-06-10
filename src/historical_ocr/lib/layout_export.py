"""Layout-aware TEI, PAGE-XML, and clean plain-text export."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, read_layout_json

TEI_NS = "http://www.tei-c.org/ns/1.0"
PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"
ET.register_namespace("", TEI_NS)
ET.register_namespace("page", PAGE_NS)
_T = f"{{{TEI_NS}}}"


def lines_to_clean_txt(lines: list[OcrLine]) -> str:
    """Single-newline plain text without layout markup."""
    return "\n".join(line.text.strip() for line in lines if line.text.strip())


def layout_result_to_clean_txt(layout: LayoutOcrResult) -> str:
    return lines_to_clean_txt(layout.lines)


def text_to_layout_result(
    text: str,
    *,
    page_width: int = 1200,
    page_height: int = 1600,
) -> LayoutOcrResult:
    lines: list[OcrLine] = []
    y = 40
    for line_num, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        lines.append(
            OcrLine(
                line_num=line_num,
                text=line,
                left=40,
                top=y,
                width=page_width - 80,
                height=24,
                conf=1.0,
            ),
        )
        y += 28
    return LayoutOcrResult(
        lines=lines,
        page_width=page_width,
        page_height=max(page_height, y + 40),
        full_text=text,
    )


def _apply_line_texts(layout: LayoutOcrResult, line_texts: list[str]) -> LayoutOcrResult:
    updated: list[OcrLine] = []
    for i, line in enumerate(layout.lines):
        text = line_texts[i] if i < len(line_texts) else line.text
        updated.append(
            OcrLine(
                line_num=line.line_num,
                text=text,
                left=line.left,
                top=line.top,
                width=line.width,
                height=line.height,
                conf=line.conf,
            ),
        )
    full_text = "\n".join(l.text for l in updated if l.text.strip())
    return LayoutOcrResult(
        lines=updated,
        page_width=layout.page_width,
        page_height=layout.page_height,
        full_text=full_text,
    )


def layout_from_clean_text(layout_path: Path, clean_text: str) -> LayoutOcrResult | None:
    layout = read_layout_json(layout_path)
    if layout is None:
        return None
    clean_lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
    if not clean_lines:
        return layout
    return _apply_line_texts(layout, clean_lines)


def lines_to_pagexml(
    page_id: str,
    image_name: str,
    layout: LayoutOcrResult,
    dst: Path,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element(f"{{{PAGE_NS}}}PcGts")
    meta = ET.SubElement(root, f"{{{PAGE_NS}}}Metadata")
    creator = ET.SubElement(meta, f"{{{PAGE_NS}}}Creator")
    creator.text = "historical-ocr"
    created = ET.SubElement(meta, f"{{{PAGE_NS}}}Created")
    created.text = page_id

    page = ET.SubElement(root, f"{{{PAGE_NS}}}Page")
    page.set("imageFilename", image_name)
    page.set("imageWidth", str(layout.page_width))
    page.set("imageHeight", str(layout.page_height))

    region = ET.SubElement(page, f"{{{PAGE_NS}}}TextRegion")
    region.set("id", f"r_{page_id}")
    region.set("custom", "readingOrder {index:0;}")

    for line in layout.lines:
        if not line.text.strip():
            continue
        text_line = ET.SubElement(region, f"{{{PAGE_NS}}}TextLine")
        text_line.set("id", f"l_{page_id}_{line.line_num}")
        text_line.set("custom", f"readingOrder {{index:{line.line_num - 1};}}")
        coords = ET.SubElement(text_line, f"{{{PAGE_NS}}}Coords")
        x1, y1 = line.left, line.top
        x2, y2 = line.left + line.width, line.top + line.height
        coords.set("points", f"{x1},{y1} {x2},{y1} {x2},{y2} {x1},{y2}")
        baseline = ET.SubElement(text_line, f"{{{PAGE_NS}}}Baseline")
        baseline.set("points", f"{x1},{y2} {x2},{y2}")
        unicode_el = ET.SubElement(text_line, f"{{{PAGE_NS}}}TextEquiv")
        unicode_el.set("conf", f"{line.conf:.2f}")
        uni = ET.SubElement(unicode_el, f"{{{PAGE_NS}}}Unicode")
        uni.text = line.text

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def lines_to_tei(
    page_id: str,
    layout: LayoutOcrResult,
    dst: Path,
    *,
    title: str | None = None,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element(f"{_T}TEI")
    header = ET.SubElement(root, f"{_T}teiHeader")
    fd = ET.SubElement(header, f"{_T}fileDesc")
    ti = ET.SubElement(fd, f"{_T}titleStmt")
    title_el = ET.SubElement(ti, f"{_T}title")
    title_el.text = title or page_id

    text_el = ET.SubElement(root, f"{_T}text")
    body = ET.SubElement(text_el, f"{_T}body")
    page_div = ET.SubElement(body, f"{_T}div", type="page")
    p = ET.SubElement(page_div, f"{_T}p")

    for line in layout.lines:
        if not line.text.strip():
            continue
        lb_id = f"lb_{page_id}_{line.line_num}"
        lb = ET.SubElement(
            p,
            f"{_T}lb",
            {
                "n": str(line.line_num),
                "xml:id": lb_id,
                "rend": "line",
                "coord": f"{line.left},{line.top},{line.width},{line.height}",
            },
        )
        lb.tail = line.text

    fac = ET.SubElement(text_el, f"{_T}facsimile")
    surface = ET.SubElement(
        fac,
        f"{_T}surface",
        {
            "ulx": "0",
            "uly": "0",
            "lrx": str(layout.page_width),
            "lry": str(layout.page_height),
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

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def export_layout_artifacts(
    page_id: str,
    image_name: str,
    layout: LayoutOcrResult,
    *,
    pagexml_path: Path,
    tei_path: Path,
    clean_txt_path: Path,
) -> None:
    lines_to_pagexml(page_id, image_name, layout, pagexml_path)
    lines_to_tei(page_id, layout, tei_path)
    clean_txt_path.write_text(layout_result_to_clean_txt(layout) + "\n", encoding="utf-8")
