"""Publication-year routing across 1500–present."""

from __future__ import annotations

from historical_ocr.document_types import infer_publication_year, suggest_print_doc_type
from historical_ocr.document_types.era_chronology import suggest_for_year
from historical_ocr.models.manifest import JobManifest, SourceRecord


def test_suggest_for_year_timeline() -> None:
    assert suggest_for_year(1550) == "early_modern_english"
    assert suggest_for_year(1620) == "early_modern_english"
    assert suggest_for_year(1750) == "enlightenment_antiqua"
    assert suggest_for_year(1850) == "nineteenth_century"
    assert suggest_for_year(1950) == "twentieth_century"
    assert suggest_for_year(2020) == "contemporary_print"


def test_suggest_with_year_and_language() -> None:
    assert suggest_print_doc_type(year=1650, language="de") == "german_fraktur"
    assert suggest_print_doc_type(year=1600, language="la") == "humanist_roman"
    assert suggest_print_doc_type(year=1880, language="en") == "nineteenth_century"


def test_infer_year_from_source_filename() -> None:
    manifest = JobManifest(
        job_id="t",
        sources=[SourceRecord(kind="file", value="/corpus/sermon_1688_scan.pdf")],
    )
    assert infer_publication_year(manifest) == 1688


def test_infer_year_from_manifest_field() -> None:
    manifest = JobManifest(job_id="t", publication_year=1923)
    assert infer_publication_year(manifest) == 1923


def test_auto_uses_manifest_year() -> None:
    manifest = JobManifest(
        job_id="t",
        publication_year=1842,
        sources=[],
    )
    assert suggest_print_doc_type(manifest=manifest) == "nineteenth_century"
