"""Glyph / letterform classification for symbol vs damage vs rule marks."""

from __future__ import annotations

import pytest

from historical_ocr.lib.glyph_classify import (
    MarkKind,
    classify_bbox,
    classify_metrics,
    classify_token,
    measure_crop,
    page_median_letter_height,
    line_median_heights,
)
from historical_ocr.lib.symbol_filter import (
    SymbolFilterOptions,
    needs_glyph_review,
    should_drop_token,
)

np = pytest.importorskip("numpy")


def _vertical_rule_crop(h: int = 80, w: int = 4) -> np.ndarray:
    arr = np.full((h, w), 255, dtype=np.uint8)
    arr[:, 1:3] = 0
    return arr


def _letter_crop(h: int = 24, w: int = 16) -> np.ndarray:
    arr = np.full((h, w), 255, dtype=np.uint8)
    arr[6:18, 5:11] = 0
    return arr


def _blob_crop(size: int = 10) -> np.ndarray:
    arr = np.full((size, size), 255, dtype=np.uint8)
    arr[1:-1, 1:-1] = 0
    return arr


def test_vertical_rule_classified_as_rule() -> None:
    metrics = measure_crop(_vertical_rule_crop(), line_median_h=24.0)
    assert metrics is not None
    decision = classify_metrics(metrics, text="|", conf=40.0)
    assert decision.kind == MarkKind.RULE
    assert decision.keep is False


def test_letter_crop_classified_as_letterform() -> None:
    metrics = measure_crop(_letter_crop(), line_median_h=24.0)
    assert metrics is not None
    decision = classify_metrics(metrics, text="n", conf=55.0)
    assert decision.kind == MarkKind.LETTERFORM
    assert decision.keep is True


def test_ink_blob_classified_as_damage() -> None:
    metrics = measure_crop(_blob_crop(), line_median_h=24.0)
    assert metrics is not None
    decision = classify_metrics(metrics, text=":", conf=35.0)
    assert decision.kind == MarkKind.DAMAGE
    assert decision.keep is False


def test_glyph_filter_overrides_blacklist_for_letterform() -> None:
    opts = SymbolFilterOptions(enabled=True, glyph_filter=True)
    from historical_ocr.lib.glyph_classify import GlyphDecision, GlyphMetrics

    decision = GlyphDecision(
        MarkKind.LETTERFORM,
        True,
        "test",
        GlyphMetrics(16, 24, 0.66, 0.3, 100, 1, 24.0, 24.0),
    )
    assert should_drop_token("l", 30.0, opts, glyph_decision=decision) is False


def test_glyph_filter_drops_rule() -> None:
    opts = SymbolFilterOptions(enabled=True, glyph_filter=True)
    from historical_ocr.lib.glyph_classify import GlyphDecision

    decision = GlyphDecision(MarkKind.RULE, False, "vertical_rule", None)
    assert should_drop_token("|", 95.0, opts, glyph_decision=decision) is True


def test_line_median_heights_from_tesseract_dict() -> None:
    data = {
        "text": ["Hello", "|", "world"],
        "conf": ["90", "30", "88"],
        "height": [20, 80, 19],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "left": [0, 0, 0],
        "top": [0, 0, 0],
        "width": [10, 2, 10],
    }
    medians = line_median_heights(data)
    assert medians[(1, 1, 1)] == pytest.approx(19.5, abs=1.0)


def test_classify_token_with_page_gray() -> None:
    page = np.full((100, 100), 255, dtype=np.uint8)
    page[10:90, 48:52] = 0
    decision = classify_token(
        text="|",
        conf=40.0,
        left=48,
        top=10,
        width=4,
        height=80,
        line_median_h=20.0,
        page_gray=page,
    )
    assert decision.kind == MarkKind.RULE
    assert decision.keep is False


def test_needs_glyph_review_for_suspect_tokens() -> None:
    opts = SymbolFilterOptions(enabled=True, glyph_filter=True)
    assert needs_glyph_review("|", 40.0, opts) is True
    assert needs_glyph_review("hello", 90.0, opts) is False


def test_bbox_fallback_vertical_rule() -> None:
    decision = classify_bbox(width=3, height=90, text="|", conf=40.0, line_median_h=22.0)
    assert decision.kind == MarkKind.RULE
    assert decision.keep is False


def test_page_median_letter_height() -> None:
    assert page_median_letter_height({(1, 1, 1): 20.0, (1, 1, 2): 22.0}) == 21.0
