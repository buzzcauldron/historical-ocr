"""Shared Google Gemini vision helpers."""

from __future__ import annotations

from historical_ocr.config import Settings


def resolve_gemini_model(settings: Settings, *, override: str | None = None) -> str:
    return override or settings.clean_llm_model or "gemini-2.5-flash"


def build_gemini_model(settings: Settings, *, model: str | None = None):
    if not settings.google_api_key:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        return None
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel(resolve_gemini_model(settings, override=model))


def transcribe_image_jpeg(
    model,
    jpeg_bytes: bytes,
    *,
    prompt: str,
    max_output_tokens: int = 512,
) -> str | None:
    try:
        resp = model.generate_content(
            [
                prompt,
                {"mime_type": "image/jpeg", "data": jpeg_bytes},
            ],
            generation_config={"temperature": 0, "max_output_tokens": max_output_tokens},
        )
    except Exception:
        return None
    text = (getattr(resp, "text", None) or "").strip()
    return text or None
