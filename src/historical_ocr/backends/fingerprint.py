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
    fp_json = scan_job / "fingerprints.json"
    if not fp_json.is_file():
        return "unknown"
    data = json.loads(fp_json.read_text(encoding="utf-8"))
    if data:
        return "print"
    return "unknown"
