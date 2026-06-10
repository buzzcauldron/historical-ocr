"""Production artifact names derived from the submitted source file."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.models.manifest import JobManifest


def stem_from_source_value(value: str) -> str:
    """Basename stem from a file path or URL (last path segment, no extension)."""
    name = Path(value).name
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def resolve_export_basename(manifest: JobManifest) -> str:
    """Stem used for ``{basename}.txt``, ``{basename}.xml``, etc."""
    if manifest.export_basename:
        return manifest.export_basename

    for rec in manifest.sources:
        if rec.kind == "file" and rec.value.strip():
            return stem_from_source_value(rec.value)

    pages = manifest.pages
    if len(pages) == 1:
        pid = pages[0].page_id
        if "_p" in pid and pid.rsplit("_p", 1)[-1].isdigit():
            return pid.rsplit("_p", 1)[0]
        return pid

    if pages:
        pids = [p.page_id for p in pages]
        if all("_p" in pid and pid.rsplit("_p", 1)[-1].isdigit() for pid in pids):
            prefix = pids[0].rsplit("_p", 1)[0]
            if all(pid.startswith(f"{prefix}_p") for pid in pids):
                return prefix
        if len({Path(p.image_path).stem for p in pages}) == 1:
            return Path(pages[0].image_path).stem

    return manifest.job_id


def production_paths(job_export_dir: Path, basename: str) -> dict[str, Path]:
    """Canonical production deliverable paths under ``export/``."""
    return {
        "txt": job_export_dir / f"{basename}.txt",
        "xml": job_export_dir / f"{basename}.xml",
        "delivery_json": job_export_dir / f"{basename}.delivery.json",
        "checksums": job_export_dir / f"{basename}.checksums.sha256",
        "corpus_jsonl": job_export_dir / "_internal" / f"{basename}.corpus.jsonl",
    }
