"""Orthogonal language × year routing."""

from __future__ import annotations

from historical_ocr.document_types import (
    apply_language_overlay,
    load_print_doc_type,
    normalize_print_language,
    resolve_doc_type_for_language_year,
    suggest_print_doc_type,
)


def test_normalize_print_language() -> None:
    assert normalize_print_language("eng") == "en"
    assert normalize_print_language("Latin") == "la"
    assert normalize_print_language("deu") == "de"
    assert normalize_print_language("greek") == "grc"
    assert normalize_print_language("Ancient Greek") == "grc"
    assert normalize_print_language("ell") == "el"
    assert normalize_print_language("modern-greek") == "el"


def test_language_year_matrix() -> None:
    assert resolve_doc_type_for_language_year("en", 1850) == "nineteenth_century"
    assert resolve_doc_type_for_language_year("de", 1720) == "german_fraktur"
    assert resolve_doc_type_for_language_year("la", 1600) == "humanist_roman"
    assert resolve_doc_type_for_language_year("fr", 1750) == "enlightenment_antiqua"
    assert resolve_doc_type_for_language_year("grc", 1600) == "greek_polytonic"
    assert resolve_doc_type_for_language_year("el", 1750) == "greek_polytonic"
    assert resolve_doc_type_for_language_year("el", 2000) == "greek_modern"


def test_suggest_combines_language_and_manifest_year() -> None:
    from historical_ocr.models.manifest import JobManifest

    m = JobManifest(job_id="t", publication_year=1680, print_language="de")
    assert suggest_print_doc_type(manifest=m) == "german_fraktur"


def test_language_overlay_swaps_tesseract_stack() -> None:
    spec = load_print_doc_type("nineteenth_century")
    overlaid = apply_language_overlay(spec, "de")
    assert "deu" in overlaid.tesseract_lang


def test_greek_doc_types_and_overlay() -> None:
    poly = load_print_doc_type("greek_polytonic")
    assert "grc" in poly.tesseract_lang
    modern = load_print_doc_type("greek_modern")
    assert "ell" in modern.tesseract_lang
    overlaid = apply_language_overlay(load_print_doc_type("nineteenth_century"), "grc")
    assert "grc" in overlaid.tesseract_lang
