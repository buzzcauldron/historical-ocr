"""Invoke manuscript-fingerprint CLI when installed on PATH."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def available() -> bool:
    return shutil.which("manuscript-fingerprint") is not None or shutil.which(
        "typebox-fingerprinter"
    ) is not None


def _cli_name() -> str:
    return "manuscript-fingerprint" if shutil.which("manuscript-fingerprint") else "typebox-fingerprinter"


def scan_pdf(
    pdf_path: Path,
    out_dir: Path,
    *,
    dpi: int = 800,
    seg_dpi: int = 300,
) -> Path:
    if not available():
        raise RuntimeError(
            "manuscript-fingerprint not on PATH. Install from manuscript-fingerprint."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        _cli_name(),
        "scan",
        str(pdf_path),
        "--out",
        str(out_dir),
        "--dpi",
        str(dpi),
        "--seg-dpi",
        str(seg_dpi),
    ]
    subprocess.run(cmd, check=True)
    return out_dir


def suggested_material(scan_job: Path) -> str:
    from historical_ocr.lib.type_routing import load_fingerprint_summary

    summary = load_fingerprint_summary(scan_job)
    if summary is None:
        return "unknown"
    return summary.suggested_material


def load_summary(scan_job: Path):
    from historical_ocr.lib.type_routing import load_fingerprint_summary

    return load_fingerprint_summary(scan_job)


def deskew_scan_pages(scan_job: Path, *, in_place: bool = True) -> int:
    """Deskew rasterized pages under scan_job/01_pages (typebox-fingerprinter layout)."""
    try:
        from manuscript_fingerprint.deskew import deskew_job_pages
    except ImportError as exc:
        raise RuntimeError(
            "deskew requires typebox-fingerprinter: pip install -e ../manuscript-fingerprint",
        ) from exc

    rows = deskew_job_pages(scan_job, in_place=in_place)
    return sum(1 for _path, meta in rows if meta.applied)
