"""Escalate hard pages to LLM clean when OCR confidence is low."""

from __future__ import annotations

from dataclasses import dataclass

from historical_ocr.config import Settings
from historical_ocr.lib.layout_ocr import LayoutOcrResult


@dataclass(frozen=True)
class EscalationDecision:
    escalate: bool
    mean_confidence: float
    low_conf_ratio: float
    dropped_glyph_ratio: float
    reason: str


def layout_confidence_stats(
    layout: LayoutOcrResult,
    *,
    original_line_count: int | None = None,
) -> tuple[float, float, float]:
    """Return (mean_conf, low_conf_ratio, dropped_glyph_ratio)."""
    confs = [ln.conf for ln in layout.lines if ln.conf >= 0]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    low_conf = sum(1 for c in confs if c < 70) / max(len(confs), 1)
    out_lines = len([ln for ln in layout.lines if ln.text.strip()])
    orig = original_line_count or out_lines or 1
    dropped = max(0.0, 1.0 - (out_lines / orig)) if orig else 0.0
    return mean_conf, low_conf, dropped


def should_escalate_to_llm_clean(
    layout: LayoutOcrResult,
    settings: Settings,
    *,
    original_line_count: int | None = None,
) -> EscalationDecision:
    """Accuracy-first: optionally run High-tier LLM clean on weak OCR."""
    if not settings.clean_llm:
        return EscalationDecision(False, 0.0, 0.0, 0.0, "llm disabled")
    if not settings.escalate_low_confidence:
        return EscalationDecision(False, 0.0, 0.0, 0.0, "escalation disabled")

    mean_conf, low_ratio, drop_ratio = layout_confidence_stats(
        layout,
        original_line_count=original_line_count,
    )
    min_mean = float(settings.escalate_min_mean_confidence)
    max_low = float(settings.escalate_max_low_conf_ratio)

    if mean_conf < min_mean:
        return EscalationDecision(
            True, mean_conf, low_ratio, drop_ratio,
            f"mean confidence {mean_conf:.1f} < {min_mean}",
        )
    if low_ratio > max_low:
        return EscalationDecision(
            True, mean_conf, low_ratio, drop_ratio,
            f"low-confidence tokens {low_ratio:.0%} > {max_low:.0%}",
        )
    return EscalationDecision(False, mean_conf, low_ratio, drop_ratio, "ok")
