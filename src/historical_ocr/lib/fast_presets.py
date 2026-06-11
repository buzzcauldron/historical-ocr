"""Runtime presets that trade optional artifacts for speed."""

from __future__ import annotations

from historical_ocr.config import Settings


def apply_low_latency_presets(settings: Settings) -> Settings:
    """Fast print OCR + Underwood rules + line/orphan sanitizer; no glyph crops or review PNG."""
    base = apply_fast_presets(settings)
    return base.model_copy(
        update={
            "clean_print": True,
            "clean_llm": None,
            "clean_llm_model": None,
            "symbol_filter": True,
            "symbol_glyph_filter": False,
            "symbol_drop_orphan_lines": True,
            "symbol_glyph_heatmap": False,
            "ocr_combination": "tesseract_then_clean",
        },
    )


def apply_fast_presets(settings: Settings) -> Settings:
    """Tune settings for minimum latency while keeping production txt+xml."""
    parallel = settings.parallel_pages if settings.parallel_pages > 0 else 4
    return settings.model_copy(
        update={
            "fast_mode": True,
            "max_image_width": min(settings.max_image_width, 2000),
            "max_image_pixels": min(settings.max_image_pixels, 8_000_000),
            "pdf_dpi": min(settings.pdf_dpi, 200),
            "jpeg_quality": min(settings.jpeg_quality, 85),
            "jpeg_optimize": False,
            "pdf_density_ocr": False,
            "clean_print": False,
            "save_layout_artifacts": False,
            "export_internal": False,
            "tei_facsimile": False,
            "parallel_pages": parallel,
            "symbol_glyph_heatmap": False,
            "figure_extract_enabled": False,
            "damage_retry_enabled": False,
            "deskew_enabled": False,
        },
    )
