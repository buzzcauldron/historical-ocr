"""bib-ocr derived helpers (density, preprocessing, optional backend)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from historical_ocr.backends import bib_ocr as bib_backend
from historical_ocr.lib.bib_section_heads import SECTION_HEADER_DENSITY_RE, SECTION_HEADER_LINE_RE
from historical_ocr.ocr.preprocess import prepare_for_tesseract


def test_section_header_patterns() -> None:
    assert SECTION_HEADER_DENSITY_RE.search("Works Cited")
    assert SECTION_HEADER_LINE_RE.search("Chapter 3  Bibliography  142")


def test_prepare_for_tesseract_inverts() -> None:
    white = Image.new("RGB", (20, 20), (250, 250, 250))
    out = prepare_for_tesseract(white, invert=True, contrast=2.0)
    px = out.getpixel((10, 10))
    assert px[0] < 128


def test_bib_ocr_backend_describe() -> None:
    text = bib_backend.describe()
    assert "bib-ocr" in text.lower()


def test_bib_ocr_extract_requires_package(tmp_path: Path) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    if bib_backend.available():
        pytest.skip("bib-ocr installed — smoke test skipped")
    with pytest.raises(RuntimeError, match="bib-ocr"):
        bib_backend.extract_citations(pdf)


@pytest.mark.skipif(
    not Path(__file__).resolve().parents[1].joinpath("tests/fixtures/sample_print.pdf").is_file(),
    reason="no sample PDF",
)
def test_pages_needing_ocr_on_fixture() -> None:
    pytest.importorskip("fitz")
    from historical_ocr.lib.bib_density import pages_needing_ocr

    pdf = Path(__file__).resolve().parents[1] / "tests/fixtures/sample_print.pdf"
    pages = pages_needing_ocr(pdf)
    assert pages is None or isinstance(pages, set)
