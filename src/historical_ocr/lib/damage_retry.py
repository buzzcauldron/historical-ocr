"""Re-OCR low-confidence line regions with stronger damage preprocess."""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.ocr.preprocess import preprocess_for_ocr

# Escalating preprocess profiles for damaged ink.
DAMAGE_PROFILES: tuple[dict, ...] = (
    {"autocontrast": True, "sharpen": True, "contrast": 1.8},
    {"autocontrast": True, "sharpen": True, "contrast": 2.5, "grayscale": True},
    {"bib_preprocess": True, "invert": True, "contrast": 2.5, "binarise": True},
)


def _rebuild_full_text(lines: list[OcrLine]) -> str:
    return "\n".join(ln.text for ln in lines if ln.text.strip())


def retry_weak_lines(
    layout: LayoutOcrResult,
    image: Path,
    *,
    lang: str,
    settings: Settings,
    conf_threshold: float | None = None,
    max_lines: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult:
    """Retry lines below confidence threshold with damage-oriented preprocess."""
    if not getattr(settings, "damage_retry_enabled", True):
        return layout
    if not layout.lines:
        return layout

    threshold = float(
        conf_threshold if conf_threshold is not None else settings.damage_retry_conf_threshold,
    )
    cap = int(max_lines if max_lines is not None else settings.damage_retry_max_lines)

    weak = [ln for ln in layout.lines if ln.conf < threshold and ln.text.strip()]
    if not weak:
        return layout
    weak = weak[:cap]

    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return layout

    from historical_ocr.backends import tesseract as tess_backend

    tess_backend.configure_from_settings(settings)
    lang = tess_backend.resolve_lang_bundle(lang, settings)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    updated = list(layout.lines)
    idx_by_num = {ln.line_num: i for i, ln in enumerate(updated)}
    retries = 0

    with Image.open(image) as page_im:
        page_im = page_im.convert("RGB")
        pad = 3
        for line in weak:
            x0 = max(0, line.left - pad)
            y0 = max(0, line.top - pad)
            x1 = min(page_im.width, line.left + line.width + pad)
            y1 = min(page_im.height, line.top + line.height + pad)
            if x1 <= x0 or y1 <= y0:
                continue
            crop = page_im.crop((x0, y0, x1, y1))
            best_text = line.text
            best_conf = line.conf

            with tempfile.TemporaryDirectory() as tmpdir:
                base = Path(tmpdir) / "line.jpg"
                crop.save(base, format="JPEG", quality=92)
                for profile in DAMAGE_PROFILES:
                    prep_path = Path(tmpdir) / f"prep_{len(profile)}.jpg"
                    prepped = preprocess_for_ocr(base, profile)
                    prepped.save(prep_path, format="JPEG", quality=92)
                    try:
                        data = pytesseract.image_to_data(
                            prepped,
                            lang=lang,
                            config="--psm 7",
                            output_type=pytesseract.Output.DICT,
                        )
                    except Exception:
                        continue
                    tokens = []
                    confs = []
                    for i, txt in enumerate(data.get("text", [])):
                        t = str(txt or "").strip()
                        if not t:
                            continue
                        try:
                            c = float(data["conf"][i])
                        except (TypeError, ValueError, KeyError):
                            c = -1.0
                        if c < 0:
                            continue
                        tokens.append(t)
                        confs.append(c)
                    if not tokens:
                        continue
                    text = " ".join(tokens)
                    mean_c = sum(confs) / len(confs)
                    if mean_c > best_conf or (mean_c >= best_conf - 2 and len(text) > len(best_text)):
                        best_text = text
                        best_conf = mean_c

            if best_conf > line.conf or (best_text != line.text and best_conf >= line.conf - 1):
                i = idx_by_num.get(line.line_num)
                if i is not None:
                    updated[i] = replace(line, text=best_text, conf=best_conf)
                    retries += 1

    if retries:
        _log(f"damage-retry: {retries} line(s) on {image.name}")
    return LayoutOcrResult(
        lines=updated,
        page_width=layout.page_width,
        page_height=layout.page_height,
        full_text=_rebuild_full_text(updated),
        sections=layout.sections,
    )
