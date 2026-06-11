"""Infer LLM provider from an API key prefix."""

from __future__ import annotations

from typing import Literal

ProviderName = Literal["anthropic", "gemini", "openai", "none"]


def detect_provider(api_key: str | None) -> ProviderName:
    key = (api_key or "").strip()
    if not key or key.startswith("sk-your") or key in {"...", "changeme"}:
        return "none"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith("gsk_"):
        return "openai"  # groq-compatible OpenAI-style; cleanup may not support yet
    return "none"


def provider_label(provider: ProviderName) -> str:
    return {
        "anthropic": "Anthropic",
        "gemini": "Google Gemini",
        "openai": "OpenAI",
        "none": "None (free / rules only)",
    }[provider]
