"""Integration: pipeline must emit per-page .txt and .xml under export/."""

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


def test_export_paths_include_txt_and_xml_dirs(print_job_export: dict) -> None:
    assert "txt_dir" in print_job_export
    assert "xml_dir" in print_job_export


def test_per_page_txt_and_xml_exist(print_job_export: dict) -> None:
    txt_dir = JOBS / print_job_export["txt_dir"]
    xml_dir = JOBS / print_job_export["xml_dir"]

    txt_files = list(txt_dir.glob("*.txt"))
    xml_files = list(xml_dir.glob("*.xml"))

    assert len(txt_files) >= 1, f"no .txt in {txt_dir}"
    assert len(xml_files) >= 1, f"no .xml in {xml_dir}"
    assert txt_files[0].stat().st_size > 0
    assert xml_files[0].stat().st_size > 0
    assert b"TEI" in xml_files[0].read_bytes()[:200]


def test_corpus_aggregates_exist(print_job_export: dict) -> None:
    assert (JOBS / print_job_export["corpus_txt"]).is_file()
    assert (JOBS / print_job_export["corpus_jsonl"]).is_file()
