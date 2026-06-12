"""Manifest checkpoints for resume and auto-restart."""

from __future__ import annotations

from historical_ocr.config import JobPaths
from historical_ocr.models.manifest import JobManifest, PageRecord


def save_manifest_checkpoint(job: JobPaths, manifest: JobManifest) -> None:
    job.ensure()
    job.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def page_ocr_complete(page: PageRecord, job: JobPaths) -> bool:
    if page.status != "ok" or not page.ocr_text_path:
        return False
    return (job.root / page.ocr_text_path).is_file()


def merge_resume_state(manifest: JobManifest, job: JobPaths) -> int:
    """Restore per-page status from an on-disk manifest. Returns pages already done."""
    path = job.manifest
    if not path.is_file():
        return 0
    try:
        prev = JobManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    prev_by_id = {p.page_id: p for p in prev.pages}
    done = 0
    for page in manifest.pages:
        old = prev_by_id.get(page.page_id)
        if old is None:
            continue
        page.status = old.status
        page.ocr_text_path = old.ocr_text_path
        page.clean_text_path = old.clean_text_path
        page.layout_path = old.layout_path
        page.pagexml_path = old.pagexml_path
        page.tei_path = old.tei_path
        page.transcription_yaml = old.transcription_yaml
        page.transcription_txt = old.transcription_txt
        page.print_doc_type = old.print_doc_type
        page.errors = list(old.errors)
        if page_ocr_complete(page, job):
            done += 1
    return done
