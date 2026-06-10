"""TXT review companions at export."""

from __future__ import annotations

import json

from historical_ocr.lib.glyph_classify import GlyphDecision, MarkKind
from historical_ocr.lib.glyph_heatmap import export_text_review, persist_glyph_decisions
from PIL import Image


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
