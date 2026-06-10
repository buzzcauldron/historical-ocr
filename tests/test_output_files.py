"""Integration: pipeline must emit production document.txt + document.xml."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = ROOT / "tests" / "fixtures" / "sample_print.pdf"
JOBS = ROOT / "jobs" / "_pytest_print"


@pytest.fixture(scope="module")
def print_job_export() -> dict:
    if not FIXTURE_PDF.is_file():
        pytest.skip("sample_print.pdf fixture missing")

    if JOBS.exists():
        import shutil

        shutil.rmtree(JOBS)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "historical_ocr.cli",
            "run",
            "_pytest_print",
            "-i",
            str(FIXTURE_PDF),
            "--mode",
            "print",
            "--no-clean",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        pytest.fail(f"historical-ocr run failed:\n{proc.stderr}\n{proc.stdout}")

    # CLI prints JSON export map to stdout (logs on stderr).
    return json.loads(proc.stdout.strip())


def test_production_deliverables_exist(print_job_export: dict) -> None:
    assert "document_txt" in print_job_export
    assert "document_xml" in print_job_export
    doc_txt = JOBS / print_job_export["document_txt"]
    doc_xml = JOBS / print_job_export["document_xml"]
    assert doc_txt.name == "sample_print.txt"
    assert doc_xml.name == "sample_print.xml"
    assert doc_txt.is_file() and doc_txt.stat().st_size > 0
    assert doc_xml.is_file() and doc_xml.stat().st_size > 0
    assert b"TEI" in doc_xml.read_bytes()[:400]
    assert "##" not in doc_txt.read_text(encoding="utf-8")


def test_delivery_manifest_and_checksums(print_job_export: dict) -> None:
    delivery = JOBS / print_job_export["delivery_json"]
    checksums = JOBS / print_job_export["checksums"]
    assert delivery.is_file()
    assert checksums.is_file()
    data = json.loads(delivery.read_text(encoding="utf-8"))
    assert data["page_count"] >= 1
    assert "document_txt" in data["deliverables"]


def test_internal_per_page_artifacts(print_job_export: dict) -> None:
    txt_dir = JOBS / print_job_export["internal_txt_dir"]
    xml_dir = JOBS / print_job_export["internal_xml_dir"]
    assert len(list(txt_dir.glob("*.txt"))) >= 1
    assert len(list(xml_dir.glob("*.xml"))) >= 1
    assert (JOBS / print_job_export["corpus_jsonl"]).is_file()
