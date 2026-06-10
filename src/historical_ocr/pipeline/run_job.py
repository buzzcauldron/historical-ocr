"""End-to-end job orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.backends import fingerprint as fp_backend
from historical_ocr.config import JobPaths, Settings
from historical_ocr.models.manifest import FingerprintSummary, JobManifest
from historical_ocr.pipeline.acquire import acquire_from_url, ingest_local
from historical_ocr.pipeline.export import export_job
from historical_ocr.pipeline.manuscript import transcribe_pages
from historical_ocr.pipeline.prepare import prepare_pages
from historical_ocr.pipeline.clean import clean_print_pages
from historical_ocr.pipeline.print_route import ocr_pages
from historical_ocr.pipeline.route import apply_routes

_PDF = ".pdf"


def run_job(
    job_id: str,
    *,
    url: str | None = None,
    inputs: list[Path] | None = None,
    settings: Settings | None = None,
    mode: str = "auto",
    prompt: Path | None = None,
    fingerprint: bool = False,
    clean: bool | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> JobManifest:
    s = settings or Settings()
    if clean is not None:
        s = s.model_copy(update={"clean_print": clean})
    job = JobPaths((s.jobs_dir / job_id).expanduser().resolve())
    job.ensure()

    manifest = JobManifest(job_id=job_id, material_mode=mode)  # type: ignore[arg-type]

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    if url:
        sources = acquire_from_url(url, job, manifest, log_fn=_log)
    elif inputs:
        sources = ingest_local(inputs, job, manifest)
    else:
        sources = sorted(job.source.iterdir()) if job.source.is_dir() else []
        if not sources:
            raise ValueError("Provide --url, --input, or populate jobs/<id>/source/")

    prepare_pages(sources, job, manifest, s)

    pdf_sources = [p for p in sources if p.suffix.lower() == _PDF]
    if fingerprint and pdf_sources:
        if not fp_backend.available():
            _log("warn: manuscript-fingerprint not on PATH — skipping fingerprint")
        else:
            scan_dir = job.fingerprint / pdf_sources[0].stem
            fp_backend.scan_pdf(
                pdf_sources[0],
                scan_dir,
                dpi=s.fingerprint_dpi,
                seg_dpi=s.fingerprint_seg_dpi,
            )
            manifest.fingerprint = FingerprintSummary(
                job_dir=str(scan_dir.relative_to(job.root)),
                suggested_material=fp_backend.suggested_material(scan_dir),  # type: ignore[arg-type]
            )

    resolved = apply_routes(manifest, mode)
    manifest.resolved_material = resolved  # type: ignore[assignment]

    needs_manuscript = resolved in ("manuscript", "mixed") or any(
        p.route == "manuscript" for p in manifest.pages
    )
    if needs_manuscript:
        if not prompt:
            raise ValueError("--prompt required for manuscript transcription")
        transcribe_pages(manifest.pages, job, manifest, s, prompt_path=prompt, log_fn=_log)

    needs_print = resolved in ("print", "mixed") or any(p.route == "print" for p in manifest.pages)
    if needs_print:
        ocr_pages(
            manifest.pages,
            job,
            manifest,
            s,
            source_pdf=pdf_sources[0] if pdf_sources else None,
            log_fn=_log,
        )
        clean_print_pages(manifest.pages, job, manifest, s, log_fn=_log)

    export_job(job, manifest)
    return manifest


def load_manifest(job_id: str, settings: Settings | None = None) -> JobManifest:
    s = settings or Settings()
    path = (s.jobs_dir / job_id / "manifest.json").expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No manifest for job {job_id}: {path}")
    return JobManifest.model_validate_json(path.read_text(encoding="utf-8"))
