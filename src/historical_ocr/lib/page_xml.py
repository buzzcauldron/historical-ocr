"""Minimal TEI P5 wrapper for plain page text (print OCR or transcription)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

TEI_NS = "http://www.tei-c.org/ns/1.0"
ET.register_namespace("", TEI_NS)
_T = f"{{{TEI_NS}}}"


def text_to_tei(page_id: str, text: str, dst: Path) -> None:
    """Write a single-page TEI document with one body paragraph."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element(f"{_T}TEI")
    header = ET.SubElement(root, f"{_T}teiHeader")
    fd = ET.SubElement(header, f"{_T}fileDesc")
    ti = ET.SubElement(fd, f"{_T}titleStmt")
    title = ET.SubElement(ti, f"{_T}title")
    title.text = page_id

    text_el = ET.SubElement(root, f"{_T}text")
    body = ET.SubElement(text_el, f"{_T}body")

    for para in text.split("\n\n"):
        block = para.strip()
        if not block:
            continue
        p = ET.SubElement(body, f"{_T}p")
        if "\n" in block:
            line_start = 1
            for line in block.split("\n"):
                line = line.strip()
                if not line:
                    continue
                lb = ET.SubElement(p, f"{_T}lb", n=str(line_start))
                lb.tail = line
                line_start += 1
        else:
            p.text = block

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
