"""OCR confusable repairs."""

from __future__ import annotations

from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.lib.ocr_confusables import apply_confusables_to_result, fix_ocr_confusables


def test_fix_canned_misread() -> None:
    assert fix_ocr_confusables("1. C ean vegetables") == "1. Canned vegetables"
    assert fix_ocr_confusables("Cean vegetables") == "Canned vegetables"
    assert fix_ocr_confusables("ean vegetables") == "Canned vegetables"


def test_fix_list_can() -> None:
    assert fix_ocr_confusables("3. ean of soup") == "3. Can of soup"


def test_apply_confusables_to_layout() -> None:
    result = LayoutOcrResult(
        lines=[OcrLine(1, "1. C ean vegetables", 10, 20, 200, 18, 80.0)],
        page_width=800,
        page_height=600,
        full_text="1. C ean vegetables",
    )
    fixed = apply_confusables_to_result(result)
    assert fixed.lines[0].text == "1. Canned vegetables"
    assert fixed.full_text == "1. Canned vegetables"


def test_preserves_clean() -> None:
    assert fix_ocr_confusables("Large clean rags") == "Large clean rags"
