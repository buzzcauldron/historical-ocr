"""Spot LLM repair for damaged OCR lines — limited calls, problem regions only."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


def _rebuild_full_text(lines: list[OcrLine]) -> str:
    return "\n".join(ln.text for ln in lines if ln.text.strip())


def _acceptable_repair(original: str, repaired: str) -> bool:
    orig = original.strip()
    new = repaired.strip()
    if not new:
        return False
    if new == orig:
        return False
    return len(new) <= len(orig) * 2 + 24 and len(new) >= max(1, len(orig) // 2)


def _resolve_provider(settings: Settings) -> str | None:
    llm = settings.clean_llm
    if llm and str(llm).lower() not in ("none", "off", "false", "0"):
        return str(llm).lower()
    if settings.google_api_key:
        return "gemini"
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    return None


def _build_cleaner(settings: Settings):
    provider = _resolve_provider(settings)
    if not provider:
        return None
    try:
        from ocr_cleanup.providers import get_cleaner
    except ImportError:
        return None

    kw: dict = {}
    if settings.clean_llm_model:
        kw["model"] = settings.clean_llm_model
    if provider == "gemini" and settings.google_api_key:
        kw["api_key"] = settings.google_api_key
    elif provider == "anthropic" and settings.anthropic_api_key:
        kw["api_key"] = settings.anthropic_api_key
    elif provider == "openai" and settings.openai_api_key:
        kw["api_key"] = settings.openai_api_key
    try:
        return get_cleaner(provider, **kw)
    except (ImportError, ValueError, RuntimeError):
        return None


def repair_weak_lines_with_llm(
    layout: LayoutOcrResult,
    *,
    settings: Settings,
    log_fn: Callable[[str], None] | None = None,
    conf_threshold: float | None = None,
    max_lines: int | None = None,
) -> LayoutOcrResult:
    """Run char-level LLM clean on a capped set of low-confidence lines."""
    if not getattr(settings, "damage_llm_enabled", False):
        return layout
    if not layout.lines:
        return layout

    cleaner = _build_cleaner(settings)
    if cleaner is None:
        return layout

    threshold = float(
        conf_threshold if conf_threshold is not None else settings.damage_llm_conf_threshold,
    )
    cap = int(max_lines if max_lines is not None else settings.damage_llm_max_lines)

    weak = [ln for ln in layout.lines if ln.conf < threshold and ln.text.strip()]
    if not weak:
        return layout
    weak = weak[:cap]

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    try:
        from ocr_cleanup.providers.base import CleaningRequest
    except ImportError:
        return layout

    updated = list(layout.lines)
    idx_by_num = {ln.line_num: i for i, ln in enumerate(updated)}
    repairs = 0

    for line in weak:
        try:
            resp = cleaner.clean(
                CleaningRequest(
                    text=line.text,
                    stage="char",
                    extra_context="Damaged newspaper scan line; fix OCR character errors only.",
                ),
            )
        except Exception:
            continue
        repaired = (resp.cleaned_text or "").strip()
        if not _acceptable_repair(line.text, repaired):
            continue
        i = idx_by_num.get(line.line_num)
        if i is None:
            continue
        updated[i] = replace(line, text=repaired, conf=max(line.conf, threshold))
        repairs += 1

    if repairs:
        _log(f"damage-llm: {repairs} line(s) repaired (≤{cap} calls)")
    return LayoutOcrResult(
        lines=updated,
        page_width=layout.page_width,
        page_height=layout.page_height,
        full_text=_rebuild_full_text(updated),
        sections=layout.sections,
    )
