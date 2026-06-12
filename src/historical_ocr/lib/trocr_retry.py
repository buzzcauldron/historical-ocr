"""Re-OCR weak Tesseract lines with Microsoft TrOCR."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


def _rebuild_full_text(lines: list[OcrLine]) -> str:
    return "\n".join(ln.text for ln in lines if ln.text.strip())


def retry_weak_lines_with_trocr(
    layout: LayoutOcrResult,
    image: Path,
    *,
    settings: Settings,
    conf_threshold: float | None = None,
    max_lines: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult:
    if not getattr(settings, "trocr_enabled", False):
        return layout
    if not layout.lines:
        return layout

    from historical_ocr.backends import trocr as trocr_backend

    if not trocr_backend.available():
        return layout

    threshold = float(
        conf_threshold if conf_threshold is not None else settings.trocr_conf_threshold,
    )
    cap = int(max_lines if max_lines is not None else settings.trocr_max_lines)
    model = getattr(settings, "trocr_model", None) or trocr_backend.DEFAULT_MODEL
    repair_conf = float(getattr(settings, "trocr_repair_conf", trocr_backend.DEFAULT_REPAIR_CONF))

    weak = [ln for ln in layout.lines if ln.conf < threshold and ln.text.strip()]
    if not weak:
        return layout
    weak = weak[:cap]

    try:
        from PIL import Image
    except ImportError:
        return layout

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    updated = list(layout.lines)
    idx_by_num = {ln.line_num: i for i, ln in enumerate(updated)}
    repairs = 0
    pad = 4

    with Image.open(image) as page_im:
        page_im = page_im.convert("RGB")
        for line in weak:
            x0 = max(0, line.left - pad)
            y0 = max(0, line.top - pad)
            x1 = min(page_im.width, line.left + line.width + pad)
            y1 = min(page_im.height, line.top + line.height + pad)
            if x1 - x0 < 8 or y1 - y0 < 6:
                continue
            crop = page_im.crop((x0, y0, x1, y1))
            try:
                text = trocr_backend.transcribe_pil(crop, model=model)
            except (OSError, RuntimeError, ValueError):
                continue
            if not text or text == line.text.strip():
                continue
            i = idx_by_num.get(line.line_num)
            if i is None:
                continue
            updated[i] = replace(line, text=text, conf=max(line.conf, repair_conf))
            repairs += 1

    if repairs:
        _log(f"trocr-retry: {repairs} line(s) on {image.name}")
    return LayoutOcrResult(
        lines=updated,
        page_width=layout.page_width,
        page_height=layout.page_height,
        full_text=_rebuild_full_text(updated),
        sections=layout.sections,
    )
