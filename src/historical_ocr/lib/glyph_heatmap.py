"""Text-review companions: glyph decisions drive TXT; heatmap PNG is export-only QA."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from historical_ocr.lib.glyph_classify import GlyphDecision, MarkKind


def page_glyph_decisions_path(job_root: Path, page_id: str) -> Path:
    return job_root / "artifacts" / page_id / "glyph_decisions.json"

_KIND_RGBA: dict[MarkKind, tuple[int, int, int, int]] = {
    MarkKind.LETTERFORM: (38, 166, 64, 100),
    MarkKind.SYMBOL: (51, 115, 217, 110),
    MarkKind.RULE: (230, 51, 38, 120),
    MarkKind.DAMAGE: (140, 26, 140, 110),
    MarkKind.UNKNOWN: (217, 140, 26, 100),
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


def render_glyph_heatmap(
    image_path: Path,
    decisions: list[tuple[int, int, int, int, GlyphDecision]],
    output_path: Path,
    *,
    title: str | None = None,
    max_width: int = _DEFAULT_MAX_WIDTH,
    dpi: int = 96,
) -> bool:
    """Downscaled QA overlay — only written beside production TXT at export."""
    del dpi, title
    dropped = [d for d in decisions if not d[4].keep]
    if not dropped:
        return False

    image_path = Path(image_path)
    output_path = Path(output_path)
    with Image.open(image_path) as im:
        base = im.convert("RGB")

    W, H = base.size
    scale = 1.0
    if W > max_width:
        scale = max_width / W
        base = base.resize((max_width, max(1, int(H * scale))), Image.BILINEAR)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for left, top, width, height, decision in dropped:
        rgba = _KIND_RGBA.get(decision.kind, _KIND_RGBA[MarkKind.UNKNOWN])
        x0 = int(left * scale)
        y0 = int(top * scale)
        x1 = x0 + max(1, int(width * scale))
        y1 = y0 + max(1, int(height * scale))
        draw.rectangle((x0, y0, x1, y1), fill=rgba, outline=rgba[:3] + (220,))

    out = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, format="PNG", optimize=True)
    return True


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


def write_text_review_json(
    dst: Path,
    *,
    companion_txt: str,
    page_id: str,
    decisions: list[dict[str, Any]],
) -> int:
    """Summary of dropped marks for human TXT review."""
    drops = _drops_only(decisions)
    payload = {
        "companion_txt": companion_txt,
        "page_id": page_id,
        "reviewed": len(decisions),
        "dropped": len(drops),
        "drops": drops,
    }
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
) -> dict[str, str]:
    """Emit review companions next to production TXT when glyph filtering dropped marks."""
    deliverables: dict[str, str] = {}
    page_summaries: list[dict[str, Any]] = []
    total_drops = 0

    for page_id, image_name in pages:
        rows = load_glyph_decisions(page_glyph_decisions_path(job_root, page_id))
        if not rows:
            continue
        drops = _drops_only(rows)
        if not drops:
            continue
        total_drops += len(drops)
        page_summaries.append({"page_id": page_id, "dropped": len(drops), "reviewed": len(rows)})

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
            decisions=rows,
        )
        if len(pages) == 1:
            deliverables["text_review_json"] = str(review_json.relative_to(job_root))

        if render_heatmap:
            image_path = pages_dir / image_name
            if image_path.is_file():
                tuples = _decisions_from_rows(rows)
                if render_glyph_heatmap(image_path, tuples, review_png, title=page_id):
                    key = "text_review_heatmap" if len(pages) == 1 else f"text_review_heatmap_{page_id}"
                    deliverables[key] = str(review_png.relative_to(job_root))

    if len(pages) > 1 and page_summaries:
        index = export_dir / f"{basename}.review.json"
        index.write_text(
            json.dumps(
                {
                    "companion_txt": str(document_txt.relative_to(job_root)),
                    "pages": page_summaries,
                    "dropped_total": total_drops,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        deliverables["text_review_json"] = str(index.relative_to(job_root))

    return deliverables if total_drops > 0 else {}
