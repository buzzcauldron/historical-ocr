"""Damage retry on weak OCR lines."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.config import Settings
from historical_ocr.lib.damage_retry import retry_weak_lines
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


def test_retry_disabled_returns_unchanged() -> None:
    layout = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="x", left=0, top=0, width=5, height=5, conf=10.0)],
        page_width=10,
        page_height=10,
        full_text="x",
    )
    s = Settings.model_construct(damage_retry_enabled=False)
    out = retry_weak_lines(layout, Path("/nonexistent.jpg"), lang="eng", settings=s)
    assert out.full_text == "x"
