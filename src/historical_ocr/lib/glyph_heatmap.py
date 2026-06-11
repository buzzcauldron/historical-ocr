"""Text-review companions: glyph + confidence heatmaps beside production TXT."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from historical_ocr.lib.glyph_classify import GlyphDecision, MarkKind

try:
    from historical_ocr.lib.ink_layout import InkLayout, render_ink_layout_heatmap
except ImportError:  # pragma: no cover
    InkLayout = None  # type: ignore[misc, assignment]
    render_ink_layout_heatmap = None  # type: ignore[misc, assignment]

try:
    from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, read_layout_json
except ImportError:  # pragma: no cover
    LayoutOcrResult = None  # type: ignore[misc, assignment]
    OcrLine = None  # type: ignore[misc, assignment]
    read_layout_json = None  # type: ignore[misc, assignment]


def page_glyph_decisions_path(job_root: Path, page_id: str) -> Path:
    return job_root / "artifacts" / page_id / "glyph_decisions.json"


_KIND_RGBA: dict[MarkKind, tuple[int, int, int, int]] = {
    MarkKind.LETTERFORM: (38, 166, 64, 100),
    MarkKind.SYMBOL: (51, 115, 217, 110),
    MarkKind.RULE: (230, 51, 38, 120),
    MarkKind.DAMAGE: (140, 26, 140, 110),
    MarkKind.STRANGE_LETTER: (255, 87, 34, 130),
    MarkKind.UNKNOWN: (217, 140, 26, 100),
}

_KEPT_RGBA: dict[MarkKind, tuple[int, int, int, int]] = {
    MarkKind.LETTERFORM: (38, 166, 64, 35),
    MarkKind.SYMBOL: (51, 115, 217, 40),
    MarkKind.RULE: (230, 51, 38, 45),
    MarkKind.DAMAGE: (140, 26, 140, 45),
    MarkKind.STRANGE_LETTER: (255, 152, 0, 55),
    MarkKind.UNKNOWN: (217, 140, 26, 40),
}

_DEFAULT_MAX_WIDTH = 1400


def persist_glyph_decisions(
    job_root: Path,
    page_id: str,
    decisions: list[tuple[int, int, int, int, GlyphDecision]],
) -> None:
    """Internal pipeline record — feeds TXT production, not a standalone deliverable."""
    if not decisions:
        return
    write_glyph_decisions_json(
        decisions,
        page_glyph_decisions_path(job_root, page_id),
        page_id=page_id,
    )


def write_glyph_decisions_json(
    decisions: list[tuple[int, int, int, int, GlyphDecision]],
    output_path: Path,
    *,
    page_id: str,
) -> None:
    payload = {
        "page_id": page_id,
        "reviewed": len(decisions),
        "decisions": [
            {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "kind": decision.kind.value,
                "keep": decision.keep,
                "reason": decision.reason,
            }
            for left, top, width, height, decision in decisions
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_glyph_decisions(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = data.get("decisions")
    return rows if isinstance(rows, list) else None


def _drops_only(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in decisions if not row.get("keep", True)]


def _confidence_rgba(conf: float) -> tuple[int, int, int, int]:
    """Green/yellow/red bands for Tesseract line confidence (0–100)."""
    c = max(0.0, min(100.0, float(conf)))
    if c >= 80:
        return (34, 139, 34, 70)
    if c >= 65:
        return (255, 193, 7, 85)
    if c >= 50:
        return (255, 140, 0, 95)
    return (220, 53, 69, 110)


def _scale_box(
    left: int,
    top: int,
    width: int,
    height: int,
    scale: float,
) -> tuple[int, int, int, int]:
    x0 = int(left * scale)
    y0 = int(top * scale)
    x1 = x0 + max(1, int(width * scale))
    y1 = y0 + max(1, int(height * scale))
    return x0, y0, x1, y1


def _draw_ink_layout_layer(
    draw: ImageDraw.ImageDraw,
    layout: InkLayout,
    *,
    scale: float,
) -> None:
    from historical_ocr.lib.ink_layout import draw_ink_layout_overlay

    draw_ink_layout_overlay(draw, layout, scale=scale)


def render_page_review_heatmap(
    image_path: Path,
    output_path: Path,
    *,
    glyph_decisions: list[tuple[int, int, int, int, GlyphDecision]] | None = None,
    layout_lines: list[Any] | None = None,
    ink_layout: InkLayout | None = None,
    title: str | None = None,
    max_width: int = _DEFAULT_MAX_WIDTH,
) -> bool:
    """QA overlay: ink layout, then OCR confidence, then glyph keep/drop."""
    del title
    glyphs = glyph_decisions or []
    lines = layout_lines or []
    if not glyphs and not lines and not (ink_layout and ink_layout.sections):
        return False

    image_path = Path(image_path)
    output_path = Path(output_path)
    with Image.open(image_path) as im:
        base = im.convert("RGB")

    w, h = base.size
    scale = 1.0
    if w > max_width:
        scale = max_width / w
        base = base.resize((max_width, max(1, int(h * scale))), Image.BILINEAR)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if ink_layout is not None and ink_layout.sections:
        _draw_ink_layout_layer(draw, ink_layout, scale=scale)

    for line in lines:
        conf = float(getattr(line, "conf", 0.0))
        left = int(getattr(line, "left", 0))
        top = int(getattr(line, "top", 0))
        width = int(getattr(line, "width", 0))
        height = int(getattr(line, "height", 0))
        if width < 1 or height < 1:
            continue
        rgba = _confidence_rgba(conf)
        x0, y0, x1, y1 = _scale_box(left, top, width, height, scale)
        draw.rectangle((x0, y0, x1, y1), fill=rgba, outline=rgba[:3] + (160,))

    for left, top, width, height, decision in glyphs:
        palette = _KIND_RGBA if not decision.keep else _KEPT_RGBA
        rgba = palette.get(decision.kind, palette[MarkKind.UNKNOWN])
        x0, y0, x1, y1 = _scale_box(left, top, width, height, scale)
        if decision.keep:
            draw.rectangle((x0, y0, x1, y1), outline=rgba[:3] + (180,), width=1)
        else:
            draw.rectangle((x0, y0, x1, y1), fill=rgba, outline=rgba[:3] + (220,))

    out = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, format="PNG", optimize=True)
    return True


def render_glyph_heatmap(
    image_path: Path,
    decisions: list[tuple[int, int, int, int, GlyphDecision]],
    output_path: Path,
    *,
    title: str | None = None,
    max_width: int = _DEFAULT_MAX_WIDTH,
    dpi: int = 96,
) -> bool:
    """Backward-compatible wrapper — glyph overlay only."""
    del dpi
    return render_page_review_heatmap(
        image_path,
        output_path,
        glyph_decisions=decisions,
        title=title,
        max_width=max_width,
    )


def _decisions_from_rows(rows: list[dict[str, Any]]) -> list[tuple[int, int, int, int, GlyphDecision]]:
    out: list[tuple[int, int, int, int, GlyphDecision]] = []
    for row in rows:
        try:
            decision = GlyphDecision(
                MarkKind(str(row["kind"])),
                bool(row["keep"]),
                str(row.get("reason", "")),
                None,
            )
            out.append(
                (
                    int(row["left"]),
                    int(row["top"]),
                    int(row["width"]),
                    int(row["height"]),
                    decision,
                ),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _ink_layout_stats(layout: InkLayout | None) -> dict[str, Any] | None:
    if layout is None or not layout.sections:
        return None
    return {
        "columns": len(layout.columns),
        "sections": len(layout.sections),
        "page_width": layout.page_width,
        "page_height": layout.page_height,
    }


def _layout_stats(lines: list[Any], *, conf_threshold: float = 65.0) -> dict[str, Any]:
    confs = [float(getattr(ln, "conf", 0.0)) for ln in lines if getattr(ln, "conf", -1) >= 0]
    if not confs:
        return {"lines": len(lines), "mean_confidence": None, "low_conf_lines": 0}
    low = sum(1 for c in confs if c < conf_threshold)
    return {
        "lines": len(lines),
        "mean_confidence": round(sum(confs) / len(confs), 2),
        "low_conf_lines": low,
        "conf_threshold": conf_threshold,
    }


def _strange_letter_decisions(decisions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        row
        for row in (decisions or [])
        if str(row.get("kind", "")) == MarkKind.STRANGE_LETTER.value
    ]


def page_needs_review(
    decisions: list[dict[str, Any]] | None,
    layout_lines: list[Any],
    *,
    conf_threshold: float = 65.0,
) -> bool:
    """True when glyph drops, strange letters, or low-confidence lines exist."""
    drops = _drops_only(decisions or [])
    if drops:
        return True
    if _strange_letter_decisions(decisions):
        return True
    for line in layout_lines:
        conf = float(getattr(line, "conf", -1.0))
        if conf >= 0 and conf < conf_threshold and str(getattr(line, "text", "")).strip():
            return True
    return False


def write_text_review_json(
    dst: Path,
    *,
    companion_txt: str,
    page_id: str,
    decisions: list[dict[str, Any]],
    layout_stats: dict[str, Any] | None = None,
    ink_layout_stats: dict[str, Any] | None = None,
) -> int:
    """Summary of glyph drops + OCR confidence for human TXT review."""
    drops = _drops_only(decisions)
    strange = _strange_letter_decisions(decisions)
    payload: dict[str, Any] = {
        "companion_txt": companion_txt,
        "page_id": page_id,
        "reviewed": len(decisions),
        "dropped": len(drops),
        "kept": len(decisions) - len(drops),
        "strange_letters": len(strange),
        "drops": drops,
        "font_flags": strange,
    }
    if layout_stats:
        payload["layout"] = layout_stats
    if ink_layout_stats:
        payload["ink_layout"] = ink_layout_stats
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(drops)


def export_text_review(
    job_root: Path,
    pages_dir: Path,
    export_dir: Path,
    *,
    basename: str,
    document_txt: Path,
    pages: list[tuple[str, str]],
    render_heatmap: bool,
    conf_threshold: float = 65.0,
) -> dict[str, str]:
    """Emit review.json + review.png only when drops or low-confidence zones exist."""
    deliverables: dict[str, str] = {}
    page_summaries: list[dict[str, Any]] = []
    total_drops = 0
    any_heatmap = False

    for page_id, image_name in pages:
        rows = load_glyph_decisions(page_glyph_decisions_path(job_root, page_id))
        layout = None
        ink_layout = None
        if read_layout_json is not None:
            from historical_ocr.pipeline.paths import page_ink_layout_json, page_layout_json
            from historical_ocr.lib.ink_layout import read_ink_layout

            layout = read_layout_json(page_layout_json(job_root, page_id))
            ink_layout = read_ink_layout(page_ink_layout_json(job_root, page_id))
        layout_lines = list(layout.lines) if layout and layout.lines else []

        if not page_needs_review(rows, layout_lines, conf_threshold=conf_threshold):
            continue

        drops = _drops_only(rows) if rows else []
        total_drops += len(drops)
        page_summaries.append(
            {
                "page_id": page_id,
                "dropped": len(drops),
                "reviewed": len(rows) if rows else 0,
                "layout": _layout_stats(layout_lines, conf_threshold=conf_threshold) if layout_lines else None,
                "ink_layout": _ink_layout_stats(ink_layout),
            },
        )

        if len(pages) == 1:
            review_json = export_dir / f"{basename}.review.json"
            review_png = export_dir / f"{basename}.review.png"
        else:
            review_dir = export_dir / "_internal" / "review"
            review_json = review_dir / f"{page_id}.review.json"
            review_png = review_dir / f"{page_id}.review.png"

        write_text_review_json(
            review_json,
            companion_txt=str(document_txt.relative_to(job_root)),
            page_id=page_id,
            decisions=rows or [],
            layout_stats=_layout_stats(layout_lines, conf_threshold=conf_threshold) if layout_lines else None,
            ink_layout_stats=_ink_layout_stats(ink_layout),
        )
        if len(pages) == 1:
            deliverables["text_review_json"] = str(review_json.relative_to(job_root))

        if render_heatmap:
            image_path = pages_dir / image_name
            if image_path.is_file():
                tuples = _decisions_from_rows(rows) if rows else []
                if render_page_review_heatmap(
                    image_path,
                    review_png,
                    glyph_decisions=tuples,
                    layout_lines=layout_lines,
                    ink_layout=ink_layout,
                    title=page_id,
                ):
                    key = "text_review_heatmap" if len(pages) == 1 else f"text_review_heatmap_{page_id}"
                    deliverables[key] = str(review_png.relative_to(job_root))
                    any_heatmap = True

    if len(pages) > 1 and page_summaries:
        index = export_dir / f"{basename}.review.json"
        index.write_text(
            json.dumps(
                {
                    "companion_txt": str(document_txt.relative_to(job_root)),
                    "pages": page_summaries,
                    "dropped_total": total_drops,
                    "heatmap": any_heatmap,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        deliverables["text_review_json"] = str(index.relative_to(job_root))

    return deliverables
