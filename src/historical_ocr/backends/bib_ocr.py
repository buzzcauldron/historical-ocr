"""Optional bib-ocr backend — bibliography citation extraction from PDFs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_extract_fn = None

try:
    from bib_ocr import extract as _extract_fn  # type: ignore[no-redef]
except ImportError:
    try:
        from bib_ocr.pipeline import extract as _extract_fn  # type: ignore[no-redef]
    except ImportError:
        pass


def available() -> bool:
    return _extract_fn is not None


def describe() -> str:
    if available():
        return "bib-ocr citation cascade (doi_scan → ref_section OCR → footnotes → inline)"
    return "not installed — pip install -e ."


def extract_citations(
    pdf_path: Path,
    *,
    max_stage: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    if not available():
        raise RuntimeError(
            "bib-ocr not installed. From a sibling checkout:\n"
            "  pip install -e .",
        )
    return _extract_fn(  # type: ignore[misc]
        pdf_path,
        max_stage=max_stage,
        verbose=verbose,
    )


def citations_to_text_block(citations: list[dict]) -> str:
    """Flatten citation dicts into a synthetic References block for downstream OCR."""
    lines: list[str] = []
    for row in citations:
        text = (row.get("text") or row.get("raw") or "").strip()
        doi = (row.get("doi") or "").strip()
        if text:
            lines.append(text)
        elif doi:
            lines.append(f"doi:{doi}")
    return "\n".join(lines)
