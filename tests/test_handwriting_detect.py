"""Handwriting detection + transcription-shell suggestion."""

from __future__ import annotations

from historical_ocr.lib.handwriting_detect import (
    assess_handwriting,
    transcription_shell_hint,
    _layout_assessment,
)
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.models.manifest import FingerprintSummary, JobManifest


def _layout(*confs: float) -> LayoutOcrResult:
    lines = [
        OcrLine(
            line_num=i + 1,
            text="ab" if c < 55 else "word here",
            left=0,
            top=i * 10,
            width=40,
            height=12,
            conf=c,
        )
        for i, c in enumerate(confs)
    ]
    return LayoutOcrResult(lines=lines, page_width=100, page_height=100, full_text="x")


def test_layout_weak_ocr_triggers_handwriting() -> None:
    result = _layout_assessment(_layout(40.0, 45.0, 50.0, 42.0))
    assert result is not None
    assert result.likely_handwriting is True


def test_layout_strong_print_not_handwriting() -> None:
    result = _layout_assessment(_layout(88.0, 90.0, 85.0))
    assert result is None


def test_fingerprint_manuscript_signal() -> None:
    fp = FingerprintSummary(suggested_material="manuscript")
    out = assess_handwriting(
        __import__("pathlib").Path("/nonexistent.jpg"),
        fingerprint=fp,
        layout=_layout(90.0, 88.0),
    )
    assert out.likely_handwriting is True
    assert out.extent == "full"
    assert "fingerprint" in out.reasons[0]


def test_transcription_shell_hint_mentions_transcriber_shell() -> None:
    msg = transcription_shell_hint(
        "page1",
        image=__import__("pathlib").Path("scan.tif"),
        job_id="job1",
        reasons=("weak OCR",),
    )
    assert "transcriber-shell run" in msg
    assert "handwriting" in msg


def test_apply_hint_on_page_record() -> None:
    from historical_ocr.lib.handwriting_detect import apply_handwriting_hint, HandwritingAssessment
    from historical_ocr.models.manifest import PageRecord

    page = PageRecord(page_id="p1", image_path="pages/p1.tif")
    manifest = JobManifest(job_id="job1")
    assessment = HandwritingAssessment(True, 0.8, ("weak OCR",), extent="full")
    apply_handwriting_hint(
        page,
        manifest,
        __import__("pathlib").Path("pages/p1.tif"),
        assessment,
    )
    assert len(page.routing_hints) == 1
    assert "transcriber-shell" in page.routing_hints[0]
