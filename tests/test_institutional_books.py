"""Institutional Books metadata filter adapter."""

from __future__ import annotations

from historical_ocr.ml.institutional_books import (
    InstitutionalBooksFilters,
    parse_publication_year,
    passes_institutional_books_filters,
    slim_record,
)
from historical_ocr.ml.tesseract_train import load_registry


def test_registry_has_institutional_books() -> None:
    reg = load_registry()
    raw = reg.get("huggingface", {}).get("institutional-books")
    assert raw is not None
    assert raw["kind"] == "metadata_only"
    assert raw.get("tesstrain") is False
    assert raw["repo"] == "institutional/institutional-books-1.0-metadata"
    assert raw.get("repo_full") == "institutional/institutional-books-1.0"


def test_parse_publication_year() -> None:
    assert parse_publication_year("1850") == 1850
    assert parse_publication_year("18uu") is None
    assert parse_publication_year("c1852") == 1852


def test_passes_filters_eng_high_ocr() -> None:
    filt = InstitutionalBooksFilters(limit=100)
    row = {
        "language_gen": "eng",
        "ocr_score_src": 88,
        "ocr_score_gen": 85,
        "date1_src": "1855",
        "likely_duplicates_barcodes_gen": [],
    }
    assert passes_institutional_books_filters(row, filt) is True


def test_rejects_low_ocr_and_duplicates() -> None:
    filt = InstitutionalBooksFilters(limit=100)
    low = {
        "language_gen": "eng",
        "ocr_score_src": 50,
        "ocr_score_gen": 85,
        "date1_src": "1855",
        "likely_duplicates_barcodes_gen": [],
    }
    dup = {
        "language_gen": "eng",
        "ocr_score_src": 90,
        "ocr_score_gen": 90,
        "date1_src": "1855",
        "likely_duplicates_barcodes_gen": ["hvd.other"],
    }
    assert passes_institutional_books_filters(low, filt) is False
    assert passes_institutional_books_filters(dup, filt) is False


def test_slim_record_omits_page_text() -> None:
    row = {
        "barcode_src": "hvd.123",
        "title_src": "Example",
        "text_by_page_src": ["should not appear"],
        "ocr_score_src": 80,
        "date1_src": "1870",
    }
    slim = slim_record(row)
    assert slim["barcode_src"] == "hvd.123"
    assert slim["publication_year_parsed"] == 1870
    assert "text_by_page_src" not in slim
