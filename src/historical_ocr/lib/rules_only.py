"""Rule-based print cleanup — no LLM providers or API keys."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.lib.symbol_filter import resolve_symbol_filter, sanitize_ocr_text


def apply_rules_only_presets(settings: Settings) -> Settings:
    """Force Tesseract + symbol/glyph filter + Underwood rules; never call an LLM."""
    return settings.model_copy(
        update={
            "fast_mode": False,
            "clean_print": True,
            "clean_llm": None,
            "clean_llm_model": None,
            "symbol_filter": True,
            "symbol_glyph_filter": True,
            "symbol_drop_orphan_lines": True,
            "ocr_combination": "tesseract_then_clean",
            "damage_retry_enabled": True,
            "symbol_glyph_heatmap": True,
            "escalate_low_confidence": False,
            "damage_llm_enabled": False,
        },
    )


def rules_only_settings(**overrides) -> Settings:
    base = apply_rules_only_presets(Settings())
    if overrides:
        base = base.model_copy(update=overrides)
    return base


def post_clean_sanitize(text: str, settings: Settings) -> str:
    """Second-pass damage drop after Underwood (orphan lines, rule junk)."""
    opts = resolve_symbol_filter(settings)
    if not opts.enabled:
        return text
    return sanitize_ocr_text(text, opts)


def apply_user_tune_rules(text: str, settings: Settings) -> str:
    if not getattr(settings, "tune_rules_path", None):
        return text
    from historical_ocr.ml.user_corrections import apply_tune_rules, load_tune_rules

    rules = load_tune_rules(settings.tune_rules_path)
    return apply_tune_rules(text, rules) if rules else text


def rules_only_clean(text: str, settings: Settings) -> str:
    """Underwood correction rules + symbol sanitizer; LLM stage is never invoked."""
    from historical_ocr.backends import ocr_cleanup as underwood

    if settings.clean_print and underwood.available():
        text = underwood.clean_text(
            text,
            apply_variants=settings.clean_apply_variants,
            rejoin_linebreaks=settings.clean_rejoin_linebreaks,
            apply_corrections=settings.clean_apply_corrections,
            llm=None,
        )
    text = post_clean_sanitize(text, settings)
    return apply_user_tune_rules(text, settings)
