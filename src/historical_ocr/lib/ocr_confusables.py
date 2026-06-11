"""Targeted OCR misread fixes for twentieth-century newsprint."""

from __future__ import annotations

import re

from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine

# Tesseract often reads the leading "C" in "Canned" as a separate glyph and
# misreads "ann" as "ean" (c/e confusion on small news type).
_CANNED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bC\s*ean(?:ned|ed)?\b", re.I), "Canned"),
    (re.compile(r"\bCean(?:ned|ed)?\b", re.I), "Canned"),
    (re.compile(r"\bean\s+vegetables\b", re.I), "Canned vegetables"),
    (re.compile(r"\b(\d+)\.\s+ean\b", re.I), r"\1. Can"),
    (re.compile(r"\bcan\s+of\s+ean\b", re.I), "can of can"),
)


def fix_ocr_confusables(text: str) -> str:
    """Apply safe, context-specific newspaper OCR repairs."""
    if not text:
        return text
    out = text
    for pattern, repl in _CANNED_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def apply_confusables_to_result(result: LayoutOcrResult) -> LayoutOcrResult:
    if not result.lines:
        fixed_full = fix_ocr_confusables(result.full_text)
        if fixed_full == result.full_text:
            return result
        return LayoutOcrResult(
            lines=result.lines,
            page_width=result.page_width,
            page_height=result.page_height,
            full_text=fixed_full,
        )

    updated: list[OcrLine] = []
    changed = False
    for line in result.lines:
        clean = fix_ocr_confusables(line.text)
        if clean != line.text:
            changed = True
        updated.append(
            OcrLine(
                line_num=line.line_num,
                text=clean,
                left=line.left,
                top=line.top,
                width=line.width,
                height=line.height,
                conf=line.conf,
            ),
        )
    if not changed:
        return result
    full_text = "\n".join(l.text for l in updated if l.text.strip())
    return LayoutOcrResult(
        lines=updated,
        page_width=result.page_width,
        page_height=result.page_height,
        full_text=full_text,
    )
