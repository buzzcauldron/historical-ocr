"""Low-confidence OCR escalation."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.lib.confidence_escalation import should_escalate_to_llm_clean
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


def _layout(*confs: float) -> LayoutOcrResult:
    lines = [
        OcrLine(
            line_num=i + 1,
            text="word",
            left=0,
            top=0,
            width=10,
            height=10,
            conf=c,
        )
        for i, c in enumerate(confs)
    ]
    return LayoutOcrResult(lines=lines, page_width=100, page_height=100, full_text="word")


def test_escalate_when_mean_confidence_low() -> None:
    s = Settings.model_construct(
        clean_llm="gemini",
        escalate_low_confidence=True,
        escalate_min_mean_confidence=80.0,
    )
    decision = should_escalate_to_llm_clean(_layout(50.0, 55.0, 60.0), s)
    assert decision.escalate is True
    assert "mean confidence" in decision.reason


def test_no_escalate_when_confidence_ok() -> None:
    s = Settings.model_construct(
        clean_llm="gemini",
        escalate_low_confidence=True,
        escalate_min_mean_confidence=70.0,
    )
    decision = should_escalate_to_llm_clean(_layout(90.0, 88.0, 92.0), s)
    assert decision.escalate is False
