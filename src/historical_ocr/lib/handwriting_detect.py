"""Detect likely handwriting on print-routed pages; suggest transcription-shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from historical_ocr.backends import transcriber_shell
from historical_ocr.lib.layout_ocr import LayoutOcrResult
from historical_ocr.models.manifest import FingerprintSummary, JobManifest

HandwritingExtent = Literal["none", "partial", "full"]


@dataclass(frozen=True)
class HandwritingAssessment:
    likely_handwriting: bool
    confidence: float
    reasons: tuple[str, ...]
    extent: HandwritingExtent = "none"
    manuscript_score: float | None = None
    weak_line_ratio: float = 0.0


def default_page_cnn_path() -> Path:
    import os

    raw = os.environ.get("HISTORICAL_OCR_PAGE_CNN_MODEL", "models/page_cnn.pt")
    return Path(raw).expanduser()


def _cnn_manuscript_score(image: Path, model_path: Path) -> tuple[str, float] | None:
    from historical_ocr.backends import page_cnn as cnn_backend

    if not image.is_file() or not cnn_backend.available(model_path):
        return None
    try:
        return cnn_backend.classify_page(image, model_path=model_path, threshold=0.5)
    except (OSError, RuntimeError, ValueError):
        return None


def _cnn_assessment(image: Path, model_path: Path) -> HandwritingAssessment | None:
    result = _cnn_manuscript_score(image, model_path)
    if result is None:
        return None
    label, score = result
    ms_score = score if label == "manuscript" else 1.0 - score
    if label == "manuscript" and score >= 0.55:
        return HandwritingAssessment(
            likely_handwriting=True,
            confidence=score,
            reasons=(f"page CNN → manuscript ({score:.0%})",),
            manuscript_score=ms_score,
        )
    if ms_score >= 0.35:
        return HandwritingAssessment(
            likely_handwriting=True,
            confidence=ms_score,
            reasons=(f"page CNN → mixed/annotation ({ms_score:.0%} manuscript)",),
            manuscript_score=ms_score,
        )
    return HandwritingAssessment(
        likely_handwriting=False,
        confidence=1.0 - ms_score,
        reasons=(),
        manuscript_score=ms_score,
    )


def _fingerprint_assessment(summary: FingerprintSummary | None) -> HandwritingAssessment | None:
    if summary is None or summary.suggested_material != "manuscript":
        return None
    return HandwritingAssessment(
        likely_handwriting=True,
        confidence=0.75,
        reasons=("type-case fingerprint → manuscript",),
    )


def _weak_line_stats(layout: LayoutOcrResult | None, *, conf_cutoff: float = 58.0) -> tuple[float, float, int]:
    if layout is None or not layout.lines:
        return 0.0, 0.0, 0
    text_lines = [ln for ln in layout.lines if ln.text.strip()]
    if not text_lines:
        return 0.0, 0.0, 0
    confs = [ln.conf for ln in text_lines if ln.conf >= 0]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    weak = sum(1 for ln in text_lines if ln.conf < conf_cutoff)
    return weak / len(text_lines), mean_conf, weak


def classify_handwriting_extent(
    *,
    likely_handwriting: bool,
    manuscript_score: float | None,
    weak_line_ratio: float,
    mean_conf: float,
    weak_line_count: int,
    fingerprint_manuscript: bool,
    full_min_manuscript_score: float = 0.72,
    partial_max_weak_ratio: float = 0.45,
    partial_min_weak_ratio: float = 0.06,
) -> HandwritingExtent:
    if fingerprint_manuscript:
        return "full"
    if manuscript_score is not None and manuscript_score >= full_min_manuscript_score:
        return "full"
    if weak_line_ratio > 0.55 and mean_conf < 52:
        return "full"
    if not likely_handwriting and weak_line_ratio < partial_min_weak_ratio:
        return "none"

    partial_signals = 0
    if manuscript_score is not None and 0.32 <= manuscript_score < full_min_manuscript_score:
        partial_signals += 1
    if partial_min_weak_ratio <= weak_line_ratio <= partial_max_weak_ratio and weak_line_count >= 2:
        partial_signals += 1
    if likely_handwriting and weak_line_ratio < partial_max_weak_ratio and weak_line_count >= 1:
        partial_signals += 1

    if partial_signals >= 1 and weak_line_ratio < 0.55:
        return "partial"
    if likely_handwriting:
        return "full"
    return "none"


def _layout_assessment(layout: LayoutOcrResult | None) -> HandwritingAssessment | None:
    if layout is None or not layout.lines:
        return None
    confs = [ln.conf for ln in layout.lines if ln.conf >= 0]
    if not confs:
        return HandwritingAssessment(
            likely_handwriting=True,
            confidence=0.6,
            reasons=("no confident OCR lines (handwriting or damage)",),
        )
    mean_conf = sum(confs) / len(confs)
    low_ratio = sum(1 for c in confs if c < 60) / len(confs)
    text_lines = [ln for ln in layout.lines if ln.text.strip()]
    short_lines = sum(1 for ln in text_lines if len(ln.text.strip()) <= 3)
    short_ratio = short_lines / max(len(text_lines), 1)

    reasons: list[str] = []
    score = 0.0
    if mean_conf < 58 and low_ratio >= 0.45:
        reasons.append(f"weak OCR (mean {mean_conf:.0f}, {low_ratio:.0%} lines <60 conf)")
        score = max(score, 0.55 + low_ratio * 0.3)
    if mean_conf < 48:
        reasons.append(f"very low OCR confidence ({mean_conf:.0f})")
        score = max(score, 0.7)
    if short_ratio >= 0.35 and mean_conf < 65:
        reasons.append(f"fragmented lines ({short_ratio:.0%} very short)")
        score = max(score, 0.5 + short_ratio * 0.2)

    if not reasons:
        return None
    return HandwritingAssessment(
        likely_handwriting=True,
        confidence=min(0.95, score),
        reasons=tuple(reasons),
    )


def assess_handwriting(
    image: Path,
    *,
    layout: LayoutOcrResult | None = None,
    fingerprint: FingerprintSummary | None = None,
    page_cnn_path: Path | None = None,
) -> HandwritingAssessment:
    """Combine CNN, fingerprint, and OCR-layout signals."""
    candidates: list[HandwritingAssessment] = []

    model = page_cnn_path or default_page_cnn_path()
    cnn = _cnn_assessment(image, model)
    if cnn and cnn.likely_handwriting:
        candidates.append(cnn)

    fp = _fingerprint_assessment(fingerprint)
    if fp:
        candidates.append(fp)

    lay = _layout_assessment(layout)
    if lay:
        candidates.append(lay)

    weak_ratio, mean_conf, weak_count = _weak_line_stats(layout)
    ms_score = next((c.manuscript_score for c in candidates if c.manuscript_score is not None), None)
    if ms_score is None and cnn is not None:
        ms_score = cnn.manuscript_score

    fp_manuscript = fingerprint is not None and fingerprint.suggested_material == "manuscript"

    if not candidates:
        extent = classify_handwriting_extent(
            likely_handwriting=False,
            manuscript_score=ms_score,
            weak_line_ratio=weak_ratio,
            mean_conf=mean_conf,
            weak_line_count=weak_count,
            fingerprint_manuscript=fp_manuscript,
        )
        if extent == "partial":
            return HandwritingAssessment(
                likely_handwriting=True,
                confidence=0.5,
                reasons=(f"sparse weak OCR lines ({weak_ratio:.0%})",),
                extent="partial",
                manuscript_score=ms_score,
                weak_line_ratio=weak_ratio,
            )
        return HandwritingAssessment(
            likely_handwriting=False,
            confidence=0.0,
            reasons=(),
            extent="none",
            manuscript_score=ms_score,
            weak_line_ratio=weak_ratio,
        )

    best = max(candidates, key=lambda a: a.confidence)
    merged_reasons: list[str] = []
    for c in candidates:
        for r in c.reasons:
            if r not in merged_reasons:
                merged_reasons.append(r)

    extent = classify_handwriting_extent(
        likely_handwriting=True,
        manuscript_score=ms_score,
        weak_line_ratio=weak_ratio,
        mean_conf=mean_conf,
        weak_line_count=weak_count,
        fingerprint_manuscript=fp_manuscript,
    )
    return HandwritingAssessment(
        likely_handwriting=extent != "none",
        confidence=best.confidence,
        reasons=tuple(merged_reasons),
        extent=extent,
        manuscript_score=ms_score,
        weak_line_ratio=weak_ratio,
    )


def transcription_shell_hint(
    page_id: str,
    *,
    image: Path,
    job_id: str,
    reasons: tuple[str, ...],
) -> str:
    """One-line log + multi-line suggestion for operators."""
    why = "; ".join(reasons) if reasons else "handwriting likely"
    install = ""
    if not transcriber_shell.available():
        install = (
            " Install transcription-shell first: "
            "pip install -e ../transcription-shell[pdf,gemini,kraken]"
        )
    cmd = (
        f"transcriber-shell run --job-id {job_id} "
        f"--image {image} --prompt /path/to/prompt.yaml --provider gemini"
    )
    return (
        f"handwriting: {page_id} — {why}. "
        f"Suggest transcription-shell for HTR (not print OCR): {cmd}.{install}"
    )


def apply_handwriting_hint(
    page,
    manifest: JobManifest,
    image: Path,
    assessment: HandwritingAssessment,
    *,
    log_fn=None,
) -> None:
    if assessment.extent != "full":
        return
    hint = transcription_shell_hint(
        page.page_id,
        image=image,
        job_id=manifest.job_id,
        reasons=assessment.reasons,
    )
    if hasattr(page, "routing_hints"):
        if hint not in page.routing_hints:
            page.routing_hints.append(hint)
    if log_fn:
        log_fn(f"hint: {hint}")
