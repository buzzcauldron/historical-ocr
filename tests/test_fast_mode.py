"""Fast runtime presets."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.lib.fast_presets import apply_fast_presets, apply_low_latency_presets


def test_apply_fast_presets() -> None:
    s = Settings(
        max_image_width=3000,
        pdf_dpi=300,
        clean_print=True,
        save_layout_artifacts=True,
        export_internal=True,
    )
    fast = apply_fast_presets(s)
    assert fast.fast_mode is True
    assert fast.max_image_width <= 2000
    assert fast.pdf_dpi <= 200
    assert fast.clean_print is False
    assert fast.save_layout_artifacts is False
    assert fast.export_internal is False
    assert fast.tei_facsimile is False
    assert fast.symbol_glyph_heatmap is False


def test_apply_low_latency_presets() -> None:
    s = Settings(clean_llm="gemini", symbol_glyph_filter=True)
    low = apply_low_latency_presets(s)
    assert low.fast_mode is True
    assert low.clean_print is True
    assert low.clean_llm is None
    assert low.symbol_glyph_filter is False
    assert low.symbol_drop_orphan_lines is True
    assert low.save_layout_artifacts is False
