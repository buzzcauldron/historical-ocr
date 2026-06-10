"""Invoke transcription-shell CLI when installed on PATH."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def available() -> bool:
    return shutil.which("transcriber-shell") is not None


def run_page(
    *,
    job_id: str,
    image: Path,
    prompt: Path,
    provider: str,
    model: str | None = None,
    lineation: str = "glyph_machina",
    doc_type: str | None = None,
    htr_combination: str | None = None,
    artifacts_dir: Path,
) -> subprocess.CompletedProcess[str]:
    if not available():
        raise RuntimeError(
            "transcriber-shell not on PATH. Install from transcription-shell "
            "or pip install transcriber-shell."
        )

    cmd = [
        "transcriber-shell",
        "run",
        "--job-id",
        job_id,
        "--image",
        str(image),
        "--prompt",
        str(prompt),
        "--provider",
        provider,
        "--lineation-backend",
        lineation,
    ]
    if model:
        cmd.extend(["--model", model])
    if doc_type:
        cmd.extend(["--doc-type", doc_type])
    if htr_combination:
        cmd.extend(["--htr-combination", htr_combination])

    env = {**os.environ, "TRANSCRIBER_SHELL_ARTIFACTS_DIR": str(artifacts_dir)}
    env["TRANSCRIBER_SHELL_TESSERACT_ENABLED"] = "1"
    return subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)


def run_print_page(
    *,
    job_id: str,
    image: Path,
    prompt: Path,
    doc_type: str,
    provider: str,
    model: str | None = None,
    lineation: str = "kraken",
    htr_combination: str = "tesseract_htr",
    artifacts_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Fork to transcription-shell for print-heavy doc_types (early modern Latin, etc.)."""
    return run_page(
        job_id=job_id,
        image=image,
        prompt=prompt,
        provider=provider,
        model=model,
        lineation=lineation,
        doc_type=doc_type,
        htr_combination=htr_combination,
        artifacts_dir=artifacts_dir,
    )


def find_lines_xml(artifacts_dir: Path, job_id: str) -> Path | None:
    candidates = [
        artifacts_dir / job_id / "lines.xml",
        artifacts_dir / job_id / "page.xml",
    ]
    for p in candidates:
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def find_transcription_yaml(artifacts_dir: Path, job_id: str, image: Path) -> Path | None:
    """Locate ``<stem>_transcription.yaml`` under artifacts/<job_id>/."""
    job_art = artifacts_dir / job_id
    candidates = [
        job_art / f"{image.stem}_transcription.yaml",
        job_art / "transcription.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    matches = sorted(job_art.glob("*_transcription.yaml"))
    return matches[0] if matches else None
