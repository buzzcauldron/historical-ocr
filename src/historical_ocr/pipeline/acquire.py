"""Acquire sources into a job directory."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from historical_ocr.config import JobPaths
from historical_ocr.lib.fetch import fetch_assets_from_url
from historical_ocr.models.manifest import JobManifest, SourceRecord


def ingest_local(paths: list[Path], job: JobPaths, manifest: JobManifest) -> list[Path]:
    job.ensure()
    saved: list[Path] = []
    for raw in paths:
        src = Path(raw).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Input not found: {src}")
        dest = job.source / src.name
        if src != dest:
            shutil.copy2(src, dest)
        saved.append(dest)
        manifest.sources.append(SourceRecord(kind="file", value=str(src)))
    return saved


def acquire_from_url(
    url: str,
    job: JobPaths,
    manifest: JobManifest,
    *,
    limit: int | None = None,
    log_fn=None,
) -> list[Path]:
    job.ensure()

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    out = job.source / "fetched"
    assets = fetch_assets_from_url(url, out, limit=limit, progress=_log)
    if not assets:
        raise RuntimeError(f"Nothing fetched from {url}")

    manifest.sources.append(
        SourceRecord(
            kind="url",
            value=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    return assets
