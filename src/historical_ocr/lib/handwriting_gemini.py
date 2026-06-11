"""Gemini vision transcription for small handwritten regions on print pages."""

from __future__ import annotations

import io
import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.lib.gemini_vision import build_gemini_model, transcribe_image_jpeg
from historical_ocr.lib.handwriting_detect import HandwritingAssessment
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine

_HW_PROMPT = """Transcribe the handwritten text in this image crop from a historical document.
The page is mostly letterpress print; this region contains handwriting (annotation, correction, or marginal note).
Return ONLY the transcribed text. Preserve original spelling and line breaks. No commentary or markdown."""

_MAX_REPLY_CHARS = 400


def _acceptable_transcription(original: str, transcribed: str) -> bool:
    new = transcribed.strip()
    if not new or len(new) > _MAX_REPLY_CHARS:
        return False
    if re.search(r"^```|^(here is|the transcription)", new, re.I):
        return False
    if new == original.strip():
        return False
    return True


def _candidate_lines(
    layout: LayoutOcrResult,
    *,
    conf_threshold: float,
    max_regions: int,
) -> list[OcrLine]:
    weak = [ln for ln in layout.lines if ln.text.strip() and ln.conf < conf_threshold]
    weak.sort(key=lambda ln: ln.conf)
    return weak[:max_regions]


def _crop_line_jpeg(page_rgb, line: OcrLine, *, pad: int = 8) -> bytes | None:
    w, h = page_rgb.size
    x0 = max(0, line.left - pad)
    y0 = max(0, line.top - pad)
    x1 = min(w, line.left + line.width + pad)
    y1 = min(h, line.top + line.height + pad)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    crop = page_rgb.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def transcribe_partial_handwriting(
    layout: LayoutOcrResult,
    image: Path,
    assessment: HandwritingAssessment,
    *,
    settings: Settings,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult:
    if assessment.extent != "partial":
        return layout
    if not getattr(settings, "handwriting_gemini_enabled", True):
        return layout
    if not settings.google_api_key or not layout.lines:
        return layout

    model = build_gemini_model(
        settings,
        model=getattr(settings, "handwriting_gemini_model", None),
    )
    if model is None:
        return layout

    threshold = float(getattr(settings, "handwriting_gemini_conf_threshold", 58.0))
    cap = int(getattr(settings, "handwriting_gemini_max_regions", 8))
    candidates = _candidate_lines(layout, conf_threshold=threshold, max_regions=cap)
    if not candidates:
        return layout

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    from PIL import Image

    updated = list(layout.lines)
    idx_by_num = {ln.line_num: i for i, ln in enumerate(updated)}
    transcribed = 0

    with Image.open(image) as im:
        page_rgb = im.convert("RGB")
        for line in candidates:
            jpeg = _crop_line_jpeg(page_rgb, line)
            if not jpeg:
                continue
            prompt = f"{_HW_PROMPT}\n\nTesseract OCR guess (may be wrong): {line.text!r}"
            text = transcribe_image_jpeg(model, jpeg, prompt=prompt)
            if not text or not _acceptable_transcription(line.text, text):
                continue
            i = idx_by_num.get(line.line_num)
            if i is None:
                continue
            updated[i] = replace(line, text=text, conf=max(line.conf, threshold + 5))
            transcribed += 1

    if transcribed:
        _log(f"handwriting-gemini: {transcribed} region(s) transcribed (≤{cap} calls)")
    full_text = "\n".join(ln.text for ln in updated if ln.text.strip())
    return LayoutOcrResult(
        lines=updated,
        page_width=layout.page_width,
        page_height=layout.page_height,
        full_text=full_text,
        sections=layout.sections,
    )
