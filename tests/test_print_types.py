"""Diachronic print document types and OCR selector."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.document_types import (
    apply_print_doc_type,
    list_print_doc_types,
    load_print_doc_type,
    suggest_print_doc_type,
)
from historical_ocr.pipeline.print_selector import PrintPlanKind, plan_print_execution


def test_list_print_doc_types() -> None:
    names = list_print_doc_types()
    assert "eebo_blackletter" in names
    assert "german_fraktur" in names


def test_load_eebo_blackletter() -> None:
    spec = load_print_doc_type("eebo_blackletter")
    assert "frk" in spec.tesseract_lang or "lat" in spec.tesseract_lang
    assert spec.ocr_model == "eebo_mixed"
    assert spec.normalization_mode == "normalized"


def test_apply_print_doc_type_diplomatic() -> None:
    spec = load_print_doc_type("humanist_roman")
    s = apply_print_doc_type(Settings(), spec)
    assert s.clean_print is False
    assert s.tesseract_lang == spec.tesseract_lang


def test_suggest_print_doc_type() -> None:
    assert suggest_print_doc_type(language="de", year=1700) == "german_fraktur"
    assert suggest_print_doc_type(language="la", year=1600) == "humanist_roman"


def test_print_selector_tesseract_then_clean() -> None:
    spec = load_print_doc_type("eebo_blackletter")
    plan = plan_print_execution(Settings(), spec, pdf_available=False)
    assert plan.kind == PrintPlanKind.TESSERACT_THEN_CLEAN
    assert plan.backends == ("tesseract",)


def test_print_selector_pdf_text_first() -> None:
    spec = load_print_doc_type("modern_historical")
    s = Settings(ocr_combination="pdf_text_first")
    plan = plan_print_execution(s, spec, pdf_available=True)
    assert plan.kind == PrintPlanKind.PDF_TEXT_FIRST
