"""Quality tiers and API key detection."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.lib.api_detect import detect_provider, provider_label
from historical_ocr.lib.quality_presets import (
    DEFAULT_QUALITY_TIER,
    apply_quality_tier,
    resolve_run_flags,
    tier_run_flags,
)


def test_detect_provider_prefixes() -> None:
    assert detect_provider("sk-ant-api03-abc") == "anthropic"
    assert detect_provider("AIzaSyABC") == "gemini"
    assert detect_provider("sk-proj-abc") == "openai"
    assert detect_provider("") == "none"
    assert provider_label("gemini") == "Google Gemini"


def test_free_tier_low_latency() -> None:
    s, prov, eff = apply_quality_tier(Settings(), "free")
    assert eff == "free"
    assert prov == "none"
    assert s.fast_mode is True
    assert s.clean_llm is None
    assert tier_run_flags("free")["low_latency"] is True


def test_medium_tier_rules_only() -> None:
    s, prov, eff = apply_quality_tier(Settings(), "medium")
    assert eff == "medium"
    assert s.symbol_glyph_filter is True
    assert s.clean_llm is None


def test_high_falls_back_without_key() -> None:
    s, prov, eff = apply_quality_tier(Settings(), "high", api_key=None)
    assert eff == "medium"
    assert s.clean_llm is None


def test_default_quality_is_medium() -> None:
    assert DEFAULT_QUALITY_TIER == "medium"
    _, flags = resolve_run_flags()
    assert flags["rules_only"] is True


def test_explicit_low_latency_overrides_quality() -> None:
    _, flags = resolve_run_flags(quality="medium", low_latency=True)
    assert flags["low_latency"] is True


def test_high_uses_spot_llm_with_key() -> None:
    s, prov, eff = apply_quality_tier(Settings(), "high", api_key="AIzaSy_test_key_12345")
    assert eff == "high"
    assert prov == "gemini"
    assert s.clean_llm is None
    assert s.damage_llm_enabled is True
    assert s.escalate_low_confidence is False
    assert s.trocr_enabled is True
    assert s.trocr_max_lines == 16
    assert s.google_api_key == "AIzaSy_test_key_12345"


def test_medium_enables_spot_llm_with_key() -> None:
    s, prov, _ = apply_quality_tier(Settings(), "medium", api_key="AIzaSy_test_key_12345")
    assert prov == "gemini"
    assert s.damage_llm_enabled is True
    assert s.handwriting_gemini_enabled is False
    assert s.damage_llm_max_lines == 8
    assert s.clean_llm is None


def test_high_caps_handwriting_gemini_regions() -> None:
    s, prov, eff = apply_quality_tier(Settings(), "high", api_key="AIzaSy_test_key_12345")
    assert eff == "high"
    assert prov == "gemini"
    assert s.handwriting_gemini_enabled is True
    assert s.handwriting_gemini_max_regions == 3
