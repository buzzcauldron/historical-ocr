"""Production document.txt + document.xml exports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from historical_ocr.lib.document_export import (
    PageSlice,
    build_delivery_manifest,
    merge_document_txt,
    write_checksums,
    write_delivery_json,
    write_document_tei,
)
from historical_ocr.models.manifest import JobManifest, PageRecord, SourceRecord


def test_merge_document_txt_no_page_headers() -> None:
    text = merge_document_txt(
        [
            PageSlice("p0", "First page line.", "a.jpg"),
            PageSlice("p1", "Second page.", "b.jpg"),
        ],
    )
    assert "##" not in text
    assert "First page line." in text
    assert "Second page." in text
    assert "\n\n" in text


def test_write_document_tei_merged(tmp_path: Path) -> None:
    manifest = JobManifest(
        job_id="demo",
        sources=[SourceRecord(kind="file", value="/tmp/book.pdf")],
        normalization_mode="normalized",
        print_doc_type="early_modern_english",
        pages=[PageRecord(page_id="book_p0000", image_path="pages/book_p0000.jpg")],
    )
    out = tmp_path / "document.xml"
    write_document_tei(
        out,
        [PageSlice("book_p0000", "Hello world", "book_p0000.jpg")],
        manifest,
    )
    raw = out.read_text(encoding="utf-8")
    assert "TEI" in raw
    assert "Hello world" in raw
    assert "historical-ocr" in raw
    assert "early_modern_english" in raw


def test_delivery_and_checksums(tmp_path: Path) -> None:
    doc = tmp_path / "document.txt"
    doc.write_text("sample\n", encoding="utf-8")
    checksums = tmp_path / "checksums.sha256"
    write_checksums(checksums, [doc])
    line = checksums.read_text(encoding="utf-8").strip()
    expected = hashlib.sha256(doc.read_bytes()).hexdigest()
    assert line.startswith(expected)

    delivery = tmp_path / "delivery.json"
    manifest = JobManifest(job_id="j1")
    write_delivery_json(
        delivery,
        build_delivery_manifest(
            manifest,
            deliverables={"document_txt": "export/document.txt"},
            page_count=3,
        ),
    )
    data = json.loads(delivery.read_text(encoding="utf-8"))
    assert data["page_count"] == 3
    assert "document_txt" in data["deliverables"]
