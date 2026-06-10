"""Minimal protocol YAML → TEI P5 (body paragraphs + line breaks).

Subset of transcription-shell ``xml_tools/tei.py`` — tables and interlinear omitted.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

TEI_NS = "http://www.tei-c.org/ns/1.0"
ET.register_namespace("", TEI_NS)
_T = f"{{{TEI_NS}}}"


def _parse_line_start(line_range: str | int | None) -> int | None:
    if line_range is None:
        return None
    part = str(line_range).split("-")[0]
    try:
        return int(part)
    except ValueError:
        return None


def yaml_to_tei(src: Path, dst: Path) -> None:
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    out = raw.get("transcriptionOutput", raw) if isinstance(raw, dict) else {}
    segs: list[dict[str, Any]] = out.get("segments", []) if isinstance(out, dict) else []
    meta = out.get("metadata", {}) if isinstance(out, dict) else {}

    root = ET.Element(f"{_T}TEI")
    text_el = ET.SubElement(root, f"{_T}text")
    body = ET.SubElement(text_el, f"{_T}body")

    if meta:
        header = ET.SubElement(root, f"{_T}teiHeader")
        fd = ET.SubElement(header, f"{_T}fileDesc")
        ti = ET.SubElement(fd, f"{_T}titleStmt")
        title = ET.SubElement(ti, f"{_T}title")
        title.text = meta.get("sourcePageId") or src.stem

    for seg in segs:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        pos = seg.get("position") or "body"
        p = ET.SubElement(body, f"{_T}p", rend=str(pos))
        line_start = _parse_line_start(seg.get("lineRange"))
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if line_start is not None and len(lines) > 1:
            for offset, line in enumerate(lines):
                lb = ET.SubElement(p, f"{_T}lb", n=str(line_start + offset))
                lb.tail = line
        else:
            p.text = text

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
