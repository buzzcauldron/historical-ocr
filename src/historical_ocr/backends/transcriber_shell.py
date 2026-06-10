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

    env = {**os.environ, "TRANSCRIBER_SHELL_ARTIFACTS_DIR": str(artifacts_dir)}
    return subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)


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
