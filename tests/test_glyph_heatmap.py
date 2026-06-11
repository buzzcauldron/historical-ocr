"""Glyph + confidence heatmap export."""

from __future__ import annotations

import json

from historical_ocr.lib.glyph_classify import GlyphDecision, MarkKind
from historical_ocr.lib.glyph_heatmap import (
    export_text_review,
    page_needs_review,
    persist_glyph_decisions,
    render_page_review_heatmap,
    write_glyph_decisions_json,
)
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from PIL import Image


def test_write_glyph_decisions_json(tmp_path) -> None:
    decisions = [
        (10, 20, 4, 80, GlyphDecision(MarkKind.RULE, False, "vertical_rule", None)),
    ]
    out = tmp_path / "page_glyph_decisions.json"
    write_glyph_decisions_json(decisions, out, page_id="page")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["page_id"] == "page"
    assert data["decisions"][0]["kind"] == "rule"
    assert data["decisions"][0]["keep"] is False


def test_heatmap_with_kept_glyphs_only(tmp_path) -> None:
    image = tmp_path / "page.jpg"
    Image.new("RGB", (120, 80), "white").save(image)
    glyphs = [(5, 5, 20, 10, GlyphDecision(MarkKind.LETTERFORM, True, "ok", None))]
    out = tmp_path / "page.review.png"
    assert render_page_review_heatmap(image, out, glyph_decisions=glyphs) is True
    assert out.is_file()


def test_export_text_review_with_layout_only(tmp_path) -> None:
    job_root = tmp_path / "job"
    pages_dir = job_root / "pages"
    export_dir = job_root / "export"
    art_dir = job_root / "artifacts" / "page"
    pages_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    art_dir.mkdir(parents=True)

    image = pages_dir / "page.tif"
    Image.new("RGB", (80, 100), "white").save(image)

    layout = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="hi", left=4, top=6, width=30, height=12, conf=55.0)],
        page_width=80,
        page_height=100,
        full_text="hi",
    )
    (art_dir / "layout.json").write_text(layout.to_json() + "\n", encoding="utf-8")

    document_txt = export_dir / "page.txt"
    document_txt.write_text("hi\n", encoding="utf-8")

    out = export_text_review(
        job_root,
        pages_dir,
        export_dir,
        basename="page",
        document_txt=document_txt,
        pages=[("page", "page.tif")],
        render_heatmap=True,
    )
    assert "text_review_heatmap" in out
    assert (export_dir / "page.review.png").is_file()
    data = json.loads((export_dir / "page.review.json").read_text(encoding="utf-8"))
    assert data["layout"]["mean_confidence"] == 55.0


def test_page_needs_review_low_confidence() -> None:
    layout = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="ok", left=0, top=0, width=10, height=10, conf=90.0)],
        page_width=10,
        page_height=10,
        full_text="ok",
    )
    assert page_needs_review([], layout.lines, conf_threshold=65.0) is False
    weak = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="weak", left=0, top=0, width=10, height=10, conf=50.0)],
        page_width=10,
        page_height=10,
        full_text="weak",
    )
    assert page_needs_review([], weak.lines, conf_threshold=65.0) is True


def test_export_skips_clean_page(tmp_path) -> None:
    job_root = tmp_path / "job"
    pages_dir = job_root / "pages"
    export_dir = job_root / "export"
    art_dir = job_root / "artifacts" / "page"
    pages_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    art_dir.mkdir(parents=True)

    image = pages_dir / "page.tif"
    Image.new("RGB", (80, 100), "white").save(image)

    layout = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="hi", left=4, top=6, width=30, height=12, conf=92.0)],
        page_width=80,
        page_height=100,
        full_text="hi",
    )
    (art_dir / "layout.json").write_text(layout.to_json() + "\n", encoding="utf-8")

    document_txt = export_dir / "page.txt"
    document_txt.write_text("hi\n", encoding="utf-8")

    out = export_text_review(
        job_root,
        pages_dir,
        export_dir,
        basename="page",
        document_txt=document_txt,
        pages=[("page", "page.tif")],
        render_heatmap=True,
        conf_threshold=65.0,
    )
    assert out == {}
    assert not (export_dir / "page.review.png").exists()


def test_export_text_review_beside_txt(tmp_path) -> None:
    job_root = tmp_path / "job"
    pages_dir = job_root / "pages"
    export_dir = job_root / "export"
    pages_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)

    image = pages_dir / "page.tif"
    Image.new("RGB", (40, 60), "white").save(image)

    persist_glyph_decisions(
        job_root,
        "page",
        [(10, 5, 3, 50, GlyphDecision(MarkKind.RULE, False, "vertical_rule", None))],
    )
    document_txt = export_dir / "page.txt"
    document_txt.write_text("hello\n", encoding="utf-8")

    out = export_text_review(
        job_root,
        pages_dir,
        export_dir,
        basename="page",
        document_txt=document_txt,
        pages=[("page", "page.tif")],
        render_heatmap=True,
    )

    assert "text_review_json" in out
    assert "text_review_heatmap" in out
    review_json = export_dir / "page.review.json"
    review_png = export_dir / "page.review.png"
    assert review_json.is_file()
    assert review_png.is_file()
    data = json.loads(review_json.read_text(encoding="utf-8"))
    assert data["dropped"] == 1
    assert data["companion_txt"] == "export/page.txt"
