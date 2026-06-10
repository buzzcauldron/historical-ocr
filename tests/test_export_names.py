"""Production artifact naming from submitted source files."""

from __future__ import annotations

from historical_ocr.lib.export_names import production_paths, resolve_export_basename
from historical_ocr.models.manifest import JobManifest, PageRecord, SourceRecord


def test_basename_from_submitted_file() -> None:
    manifest = JobManifest(
        job_id="_downloads_blacknews",
        sources=[SourceRecord(kind="file", value="/Users/me/Downloads/BlackNews_19700110_002.tif")],
        pages=[PageRecord(page_id="BlackNews_19700110_002", image_path="pages/BlackNews_19700110_002.jpg")],
    )
    assert resolve_export_basename(manifest) == "BlackNews_19700110_002"


def test_basename_from_pdf_pages() -> None:
    manifest = JobManifest(
        job_id="_pytest_print",
        sources=[SourceRecord(kind="file", value="/tmp/sample_print.pdf")],
        pages=[
            PageRecord(page_id="sample_print_p0000", image_path="pages/sample_print_p0000.jpg"),
            PageRecord(page_id="sample_print_p0001", image_path="pages/sample_print_p0001.jpg"),
        ],
    )
    assert resolve_export_basename(manifest) == "sample_print"


def test_production_paths_use_basename(tmp_path) -> None:
    paths = production_paths(tmp_path / "export", "BlackNews_19700110_002")
    assert paths["txt"].name == "BlackNews_19700110_002.txt"
    assert paths["xml"].name == "BlackNews_19700110_002.xml"
    assert paths["delivery_json"].name == "BlackNews_19700110_002.delivery.json"
    assert paths["checksums"].name == "BlackNews_19700110_002.checksums.sha256"
