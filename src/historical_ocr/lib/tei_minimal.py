"""Minimal protocol YAML → TEI P5 (body paragraphs + line breaks + figures).

Subset of transcription-shell ``xml_tools/tei.py`` — tables and interlinear omitted.
``[fig:id]`` protocol markers become TEI ``<figure>`` elements when crop metadata exists.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

TEI_NS = "http://www.tei-c.org/ns/1.0"
ET.register_namespace("", TEI_NS)
_T = f"{{{TEI_NS}}}"
_FIG_RE = re.compile(r"^\[fig:([^\]]+)\]$")


def _parse_line_start(line_range: str | int | None) -> int | None:
    if line_range is None:
        return None
    part = str(line_range).split("-")[0]
    try:
        return int(part)
    except ValueError:
        return None


def _figures_by_id(out: dict[str, Any]) -> dict[str, dict[str, Any]]:
    figs = out.get("figures") or []
    if not isinstance(figs, list):
        return {}
    return {str(f["id"]): f for f in figs if isinstance(f, dict) and f.get("id")}


def _append_line_content(
    parent: ET.Element,
    line: str,
    *,
    fig_lookup: dict[str, dict[str, Any]],
    line_num: int | None,
) -> None:
    m = _FIG_RE.match(line.strip())
    if m:
        fig_id = m.group(1)
        meta = fig_lookup.get(fig_id, {})
        fig = ET.SubElement(parent, f"{_T}figure")
        fig.set("{http://www.w3.org/XML/1998/namespace}id", fig_id)
        if meta.get("label"):
            head = ET.SubElement(fig, f"{_T}head")
            head.text = str(meta["label"])
        crop = meta.get("crop_path")
        if crop:
            graphic = ET.SubElement(fig, f"{_T}graphic")
            graphic.set("url", str(crop))
        return

    if line_num is not None:
        lb = ET.SubElement(parent, f"{_T}lb", n=str(line_num))
        lb.tail = line
    else:
        if parent.text:
            parent.text = (parent.text or "") + "\n" + line
        else:
            parent.text = line


def _segment_to_p(body: ET.Element, seg: dict[str, Any], fig_lookup: dict[str, dict[str, Any]]) -> None:
    text = (seg.get("text") or "").strip()
    if not text:
        return
    pos = seg.get("position") or "body"
    p = ET.SubElement(body, f"{_T}p", rend=str(pos))
    line_start = _parse_line_start(seg.get("lineRange"))
    lines = text.split("\n")
    content = [(off, ln) for off, ln in enumerate(lines) if ln.strip() or _FIG_RE.match(ln.strip())]
    if not content:
        return
    if len(content) == 1 and line_start is None and not _FIG_RE.match(content[0][1].strip()):
        p.text = content[0][1]
        return
    p.text = None
    for off, line in content:
        n = (line_start + off) if line_start is not None else None
        _append_line_content(p, line, fig_lookup=fig_lookup, line_num=n)


def yaml_to_tei(src: Path, dst: Path) -> None:
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    out = raw.get("transcriptionOutput", raw) if isinstance(raw, dict) else {}
    segs: list[dict[str, Any]] = out.get("segments", []) if isinstance(out, dict) else []
    meta = out.get("metadata", {}) if isinstance(out, dict) else {}
    fig_lookup = _figures_by_id(out) if isinstance(out, dict) else {}

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
        if isinstance(seg, dict):
            _segment_to_p(body, seg, fig_lookup)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
