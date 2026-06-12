"""Free / medium / high quality tiers — accuracy first, speed second."""

from __future__ import annotations

from typing import Literal

from historical_ocr.config import Settings
from historical_ocr.lib.api_detect import ProviderName, detect_provider
from historical_ocr.lib.fast_presets import apply_low_latency_presets
from historical_ocr.lib.rules_only import apply_rules_only_presets

QualityTier = Literal["free", "medium", "high"]

DEFAULT_QUALITY_TIER: QualityTier = "medium"
_TIER_ORDER: tuple[QualityTier, ...] = ("free", "medium", "high")


def tier_label(tier: QualityTier) -> str:
    return {
        "free": "Free — rules + tune, no LLM (~5 s/page)",
        "medium": "Medium — glyph filter + rules + spot LLM on damage if key (~6–12 s/page)",
        "high": "High — medium + full damage LLM + handwriting (~10–20 s/page)",
    }[tier]


def tier_run_flags(tier: QualityTier) -> dict:
    """Flags passed to ``run_job`` for the chosen tier."""
    if tier == "free":
        return {"low_latency": True, "rules_only": False, "fast": False}
    if tier == "medium":
        return {"low_latency": False, "rules_only": True, "fast": False}
    return {"low_latency": False, "rules_only": False, "fast": False}


def apply_quality_tier(
    settings: Settings,
    tier: QualityTier,
    *,
    api_key: str | None = None,
) -> tuple[Settings, ProviderName, QualityTier]:
    """Return settings + effective provider/tier (high may fall back if no key)."""
    provider = detect_provider(api_key)
    effective = tier

    if tier == "free":
        s = apply_low_latency_presets(settings)
        return s.model_copy(
            update={
                "clean_llm": None,
                "figure_extract_enabled": False,
                "damage_retry_enabled": False,
                "deskew_enabled": False,
            },
        ), "none", effective

    accuracy_flags = {
        "figure_extract_enabled": True,
        "damage_retry_enabled": True,
        "deskew_enabled": True,
        "overlaid_ocr_enabled": True,
    }

    if tier == "medium":
        s = apply_rules_only_presets(settings)
        spot_llm = _spot_llm_flags(provider, api_key, tier="medium")
        medium_updates: dict = {
            "clean_llm": None,
            "text_slice_only": True,
            **accuracy_flags,
            **spot_llm,
        }
        if api_key and provider in ("gemini", "anthropic", "openai"):
            s = _inject_api_key(s, provider, api_key)
            medium_updates["clean_llm_model"] = _default_model(provider, tier="medium")
        return s.model_copy(update=medium_updates), provider if api_key else "none", effective

    # high — spot LLM on damaged lines; fall back to medium without API
    if provider == "none":
        effective = "medium"
        s = apply_rules_only_presets(settings)
        return s.model_copy(update={
            "clean_llm": None,
            "text_slice_only": True,
            **accuracy_flags,
            "damage_llm_enabled": False,
        }), "none", effective

    s = apply_rules_only_presets(settings)
    s = _inject_api_key(s, provider, api_key)
    model = _default_model(provider, tier="high")
    spot_llm = _spot_llm_flags(provider, api_key, tier="high")
    return s.model_copy(
        update={
            "clean_llm": None,
            "clean_llm_model": model,
            "clean_print": True,
            "escalate_low_confidence": False,
            **accuracy_flags,
            **spot_llm,
        },
    ), provider, effective


def _inject_api_key(settings: Settings, provider: ProviderName, api_key: str) -> Settings:
    if provider == "anthropic":
        return settings.model_copy(update={"anthropic_api_key": api_key})
    if provider == "gemini":
        return settings.model_copy(update={"google_api_key": api_key})
    if provider == "openai":
        return settings.model_copy(update={"openai_api_key": api_key})
    return settings


def resolve_run_flags(
    *,
    quality: QualityTier | None = None,
    fast: bool = False,
    rules_only: bool = False,
    low_latency: bool = False,
) -> tuple[QualityTier, dict]:
    """Explicit speed flags win; otherwise use *quality* (default medium)."""
    if low_latency:
        return "free", tier_run_flags("free")
    if rules_only:
        return "medium", tier_run_flags("medium")
    if fast:
        return "free", {"low_latency": False, "rules_only": False, "fast": True}
    tier: QualityTier = quality or DEFAULT_QUALITY_TIER
    return tier, tier_run_flags(tier)


def apply_tier_for_run(
    settings: Settings,
    tier: QualityTier,
    *,
    api_key: str | None = None,
) -> Settings:
    """Settings after quality tier (for OCR eval or run_job)."""
    updated, _, effective = apply_quality_tier(settings, tier, api_key=api_key)
    flags = tier_run_flags(effective)
    if flags.get("low_latency"):
        return apply_low_latency_presets(updated)
    if flags.get("rules_only"):
        return apply_rules_only_presets(updated)
    if flags.get("fast"):
        from historical_ocr.lib.fast_presets import apply_fast_presets

        return apply_fast_presets(updated)
    return updated


def _default_model(provider: ProviderName, *, tier: QualityTier = "high") -> str | None:
    if tier == "medium":
        # Spot repair on ≤8 lines — use fastest/cheapest model.
        return {
            "anthropic": "claude-haiku-4-5-20251001",
            "gemini": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
        }.get(provider)
    return {
        "anthropic": "claude-sonnet-4-6",
        "gemini": "gemini-2.5-pro",
        "openai": "gpt-4o",
    }.get(provider)


def _spot_llm_flags(provider: ProviderName, api_key: str | None, *, tier: QualityTier) -> dict:
    """Limited per-line LLM for damaged OCR — not full-page clean."""
    if not api_key or provider == "none":
        return {
            "damage_llm_enabled": False,
            "escalate_low_confidence": False,
            "handwriting_gemini_enabled": False,
        }
    if tier == "medium":
        return {
            "damage_llm_enabled": True,
            "escalate_low_confidence": False,
            "handwriting_gemini_enabled": False,
            "damage_llm_max_lines": 8,
        }
    return {
        "damage_llm_enabled": True,
        "escalate_low_confidence": False,
        "handwriting_gemini_enabled": provider == "gemini",
        "handwriting_gemini_max_regions": 3,
        "trocr_enabled": True,
        "trocr_max_lines": 16,
    }
