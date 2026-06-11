"""Partial handwriting → Gemini region transcription."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from historical_ocr.config import Settings
from historical_ocr.lib.handwriting_detect import (
    HandwritingAssessment,
    classify_handwriting_extent,
)
from historical_ocr.lib.handwriting_gemini import transcribe_partial_handwriting
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from PIL import Image


def _layout() -> LayoutOcrResult:
    return LayoutOcrResult(
        lines=[
            OcrLine(1, "printed line ok", 10, 10, 120, 14, 92.0),
            OcrLine(2, "scribble", 10, 40, 80, 14, 42.0),
        ],
        page_width=200,
        page_height=100,
        full_text="printed line ok\nscribble",
    )


def test_classify_partial_mixed_page() -> None:
    assert (
        classify_handwriting_extent(
            likely_handwriting=True,
            manuscript_score=0.42,
            weak_line_ratio=0.25,
            mean_conf=75.0,
            weak_line_count=3,
            fingerprint_manuscript=False,
        )
        == "partial"
    )


def test_classify_full_manuscript_cnn() -> None:
    assert (
        classify_handwriting_extent(
            likely_handwriting=True,
            manuscript_score=0.8,
            weak_line_ratio=0.2,
            mean_conf=70.0,
            weak_line_count=2,
            fingerprint_manuscript=False,
        )
        == "full"
    )


def test_partial_skips_transcription_shell_hint() -> None:
    from historical_ocr.lib.handwriting_detect import apply_handwriting_hint
    from historical_ocr.models.manifest import JobManifest, PageRecord

    page = PageRecord(page_id="p1", image_path="pages/p1.tif")
    assessment = HandwritingAssessment(
        True,
        0.5,
        ("mixed",),
        extent="partial",
        manuscript_score=0.4,
        weak_line_ratio=0.2,
    )
    apply_handwriting_hint(
        page,
        JobManifest(job_id="job1"),
        Path("pages/p1.tif"),
        assessment,
    )
    assert page.routing_hints == []


def test_transcribe_partial_handwriting_mock(tmp_path: Path) -> None:
    image = tmp_path / "page.jpg"
    Image.new("RGB", (200, 100), "white").save(image)
    layout = _layout()
    assessment = HandwritingAssessment(
        True,
        0.5,
        ("mixed",),
        extent="partial",
    )
    settings = Settings.model_construct(
        google_api_key="test-key",
        handwriting_gemini_enabled=True,
        handwriting_gemini_conf_threshold=55.0,
    )

    mock_model = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "handwritten note"
    mock_model.generate_content.return_value = mock_resp

    with patch(
        "historical_ocr.lib.handwriting_gemini.build_gemini_model",
        return_value=mock_model,
    ):
        out = transcribe_partial_handwriting(
            layout,
            image,
            assessment,
            settings=settings,
        )

    assert "handwritten note" in out.full_text
    assert mock_model.generate_content.called


def test_full_extent_does_not_call_gemini(tmp_path: Path) -> None:
    image = tmp_path / "page.jpg"
    Image.new("RGB", (200, 100), "white").save(image)
    assessment = HandwritingAssessment(True, 0.9, ("full page",), extent="full")
    settings = Settings.model_construct(google_api_key="test-key", handwriting_gemini_enabled=True)
    layout = _layout()

    with patch(
        "historical_ocr.lib.handwriting_gemini.build_gemini_model",
        return_value=MagicMock(),
    ) as build:
        out = transcribe_partial_handwriting(layout, image, assessment, settings=settings)
    build.assert_not_called()
    assert out.full_text == layout.full_text
