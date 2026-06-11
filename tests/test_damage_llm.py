"""Spot LLM repair on weak OCR lines."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from historical_ocr.config import Settings
from historical_ocr.lib.damage_llm import repair_weak_lines_with_llm
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


@dataclass
class _FakeResponse:
    cleaned_text: str


def _layout(*pairs: tuple[str, float]) -> LayoutOcrResult:
    lines = [
        OcrLine(
            line_num=i + 1,
            text=text,
            left=0,
            top=i * 10,
            width=50,
            height=8,
            conf=conf,
        )
        for i, (text, conf) in enumerate(pairs)
    ]
    return LayoutOcrResult(
        lines=lines,
        page_width=100,
        page_height=100,
        full_text="\n".join(ln.text for ln in lines),
    )


def test_damage_llm_disabled_returns_unchanged() -> None:
    layout = _layout(("broken l1ne", 40.0))
    s = Settings.model_construct(damage_llm_enabled=False)
    out = repair_weak_lines_with_llm(layout, settings=s)
    assert out.full_text == layout.full_text


def test_damage_llm_repairs_weak_lines_only() -> None:
    layout = _layout(("good line", 90.0), ("broken l1ne", 40.0))
    s = Settings.model_construct(
        damage_llm_enabled=True,
        google_api_key="test-key",
        damage_llm_conf_threshold=55.0,
        damage_llm_max_lines=5,
    )
    cleaner = MagicMock()
    cleaner.clean.return_value = _FakeResponse(cleaned_text="broken line")

    with patch("historical_ocr.lib.damage_llm._build_cleaner", return_value=cleaner):
        out = repair_weak_lines_with_llm(layout, settings=s)

    assert "good line" in out.full_text
    assert "broken line" in out.full_text
    assert cleaner.clean.call_count == 1
