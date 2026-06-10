"""Glyph artifact export."""

from __future__ import annotations

import json

from historical_ocr.lib.glyph_classify import GlyphDecision, MarkKind
from historical_ocr.lib.glyph_heatmap import write_glyph_decisions_json


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
