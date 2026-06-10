"""End-to-end job orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.backends import fingerprint as fp_backend
from historical_ocr.config import JobPaths, Settings
from historical_ocr.models.manifest import FingerprintSummary, JobManifest
from historical_ocr.pipeline.acquire import acquire_from_url, ingest_local
from historical_ocr.lib.fast_presets import apply_fast_presets
from historical_ocr.pipeline.export import export_job
from historical_ocr.pipeline.manuscript import transcribe_pages
from historical_ocr.pipeline.prepare import prepare_pages
from historical_ocr.pipeline.clean import clean_print_pages
from historical_ocr.document_types.print_types import apply_print_doc_type
from historical_ocr.pipeline.print_route import ocr_pages, resolve_print_spec
from historical_ocr.pipeline.route import apply_routes

_PDF = ".pdf"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


def _discover_sources(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        return []
    allowed = _IMAGE_SUFFIXES | {_PDF}
    return sorted(
        p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() in allowed
    )


def run_job(
    job_id: str,
    *,
    url: str | None = None,
    limit: int | None = None,
    inputs: list[Path] | None = None,
    settings: Settings | None = None,
    mode: str = "auto",
    prompt: Path | None = None,
    fingerprint: bool = False,
    clean: bool | None = None,
    print_doc_type: str | None = None,
    ocr_combination: str | None = None,
    publication_year: int | None = None,
    print_language: str | None = None,
    extract_figures: bool = False,
    fast: bool = False,
    symbol_filter: bool | None = None,
    glyph_heatmap: bool | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> JobManifest:
    s = settings or Settings()
    if fast or s.fast_mode:
        s = apply_fast_presets(s)
    updates: dict = {}
    if extract_figures:
        updates["figure_extract_enabled"] = True
    if clean is not None:
        updates["clean_print"] = clean
    if symbol_filter is not None:
        updates["symbol_filter"] = symbol_filter
    if glyph_heatmap is not None:
        updates["symbol_glyph_heatmap"] = glyph_heatmap
    if print_doc_type:
        updates["print_doc_type"] = print_doc_type
    if ocr_combination:
        updates["ocr_combination"] = ocr_combination
    if publication_year is not None:
        updates["publication_year"] = publication_year
    if print_language:
        updates["print_language"] = print_language
    if updates:
        s = s.model_copy(update=updates)
    job = JobPaths((s.jobs_dir / job_id).expanduser().resolve())
    job.ensure()

    manifest = JobManifest(
        job_id=job_id,
        material_mode=mode,  # type: ignore[arg-type]
        publication_year=s.publication_year or publication_year,
        print_language=print_language if print_language is not None else s.print_language,
    )

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    if url:
        sources = acquire_from_url(url, job, manifest, limit=limit, log_fn=_log)
    elif inputs:
        sources = ingest_local(inputs, job, manifest)
    else:
        sources = _discover_sources(job.source)
        if not sources:
            raise ValueError("Provide --url, --input, or populate jobs/<id>/source/")

    prepare_pages(sources, job, manifest, s)

    pdf_sources = [p for p in sources if p.suffix.lower() == _PDF]
    if pdf_sources and s.pdf_density_ocr:
        from historical_ocr.lib.print_ocr import save_pdf_density_artifact

        out = job.artifacts / f"{pdf_sources[0].stem}_density.png"
        if save_pdf_density_artifact(pdf_sources[0], out):
            _log(f"artifact: {out.relative_to(job.root)}")

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

    resolved = apply_routes(
        manifest,
        mode,
        job_root=job.root,
        settings=s,
        log_fn=_log,
    )
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
        print_spec = resolve_print_spec(s, manifest)
        manifest.print_language = s.print_language
        s = apply_print_doc_type(s, print_spec)
        if clean is not None:
            s = s.model_copy(update={"clean_print": clean})
        if ocr_combination:
            s = s.model_copy(update={"ocr_combination": ocr_combination})
        manifest.normalization_mode = s.normalization_mode
        ocr_pages(
            manifest.pages,
            job,
            manifest,
            s,
            source_pdf=pdf_sources[0] if pdf_sources else None,
            print_spec=print_spec,
            prompt_path=prompt,
            log_fn=_log,
        )
        clean_print_pages(manifest.pages, job, manifest, s, log_fn=_log)

    export_job(
        job,
        manifest,
        export_internal=s.export_internal,
        tei_facsimile=s.tei_facsimile,
        settings=s,
    )
    return manifest


def load_manifest(job_id: str, settings: Settings | None = None) -> JobManifest:
    s = settings or Settings()
    path = (s.jobs_dir / job_id / "manifest.json").expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No manifest for job {job_id}: {path}")
    return JobManifest.model_validate_json(path.read_text(encoding="utf-8"))
