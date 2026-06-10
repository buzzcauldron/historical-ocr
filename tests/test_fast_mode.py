"""Fast runtime presets."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.lib.fast_presets import apply_fast_presets


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
