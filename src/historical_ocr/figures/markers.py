"""Insert ``[fig:id]`` markers into a finished transcription YAML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import yaml

from historical_ocr.figures.base import FigureResult


def _xml_namespace(element: ET.Element) -> str:
    m = re.match(r"\{.*\}", element.tag)
    return m.group(0)[1:-1] if m else ""


def _line_centers_y(lines_xml_path: Path) -> list[tuple[int, float]]:
    tree = ET.parse(str(lines_xml_path))
    root = tree.getroot()
    ns = {"ns": _xml_namespace(root)}
    out: list[tuple[int, float]] = []
    n = 0
    for line in root.findall(".//ns:TextLine", ns):
        if line.get("custom") == "type {type:margin;}":
            continue
        coords = line.find("ns:Coords", ns)
        if coords is None or not coords.get("points"):
            continue
        ys: list[float] = []
        for tok in coords.get("points", "").split():
            if "," not in tok:
                continue
            try:
                ys.append(float(tok.split(",", 1)[1]))
            except ValueError:
                continue
        if not ys:
            continue
        n += 1
        out.append((n, sum(ys) / len(ys)))
    return out


def _figure_anchor_line(
    figure_bbox: tuple[int, int, int, int],
    line_centers: list[tuple[int, float]],
) -> int:
    if not line_centers:
        return 0
    top_y = float(figure_bbox[1])
    above = [n for (n, yc) in line_centers if yc < top_y]
    if not above:
        return 0
    return max(above)


def _insert_marker_in_segment_text(text: str, after_line_in_segment_idx: int, marker: str) -> str:
    lines = text.split("\n")
    insertion_point = max(0, min(len(lines), after_line_in_segment_idx + 1))
    lines.insert(insertion_point, marker)
    return "\n".join(lines)


def insert_markers(
    *,
    yaml_path: Path,
    lines_xml_path: Path | None,
    figures: Iterable[FigureResult],
) -> tuple[int, int]:
    """Rewrite ``yaml_path`` in place to add ``[fig:id]`` markers + figures section."""
    figs = list(figures)
    if not figs:
        return 0, 0

    yaml_path = Path(yaml_path).expanduser().resolve()
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    root = data.get("transcriptionOutput") if isinstance(data, dict) and "transcriptionOutput" in data else data
    if not isinstance(root, dict):
        return 0, 0

    segments = root.get("segments")
    if not isinstance(segments, list):
        segments = []

    seg_for_line: dict[int, int] = {}
    for seg_idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        lr = seg.get("lineRange")
        if isinstance(lr, list) and len(lr) == 2:
            try:
                lo, hi = int(lr[0]), int(lr[1])
            except (TypeError, ValueError):
                continue
            for ln in range(lo, hi + 1):
                seg_for_line.setdefault(ln, seg_idx)

    line_centers = _line_centers_y(lines_xml_path) if lines_xml_path and Path(lines_xml_path).is_file() else []
    figs_sorted = sorted(figs, key=lambda f: f.bbox[1])

    inserted = 0
    for f in figs_sorted:
        anchor_line = _figure_anchor_line(f.bbox, line_centers)
        seg_idx: int | None
        if anchor_line == 0:
            seg_idx = 0 if segments else None
        else:
            seg_idx = seg_for_line.get(anchor_line)
            if seg_idx is None and segments:
                seg_idx = len(segments) - 1
        if seg_idx is None:
            continue
        seg = segments[seg_idx]
        if not isinstance(seg, dict):
            continue
        text = seg.get("text", "")
        if not isinstance(text, str):
            continue
        lr = seg.get("lineRange") or [0, 0]
        try:
            seg_lo = int(lr[0])
        except (TypeError, ValueError):
            seg_lo = 1
        within = (anchor_line - seg_lo) if anchor_line > 0 else -1
        marker = f"[fig:{f.id}]"
        seg["text"] = _insert_marker_in_segment_text(text, within, marker)
        inserted += 1

    fig_section = []
    for f in figs_sorted:
        entry: dict = {
            "id": f.id,
            "bbox_page_px": list(f.bbox),
            "label": f.label,
            "detector_confidence": round(f.confidence, 3),
        }
        if f.crop_path is not None:
            entry["crop_path"] = str(f.crop_path)
        if f.notes:
            entry["notes"] = f.notes
        fig_section.append(entry)
    root["figures"] = fig_section

    yaml_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return inserted, len(figs_sorted)
