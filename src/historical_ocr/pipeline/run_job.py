"""End-to-end job orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.config import JobPaths, Settings
from historical_ocr.models.manifest import JobManifest
from historical_ocr.pipeline.acquire import acquire_from_url, ingest_local
from historical_ocr.lib.fast_presets import apply_fast_presets, apply_low_latency_presets
from historical_ocr.lib.quality_presets import DEFAULT_QUALITY_TIER, apply_tier_for_run, resolve_run_flags
from historical_ocr.lib.rules_only import apply_rules_only_presets
from historical_ocr.pipeline.export import export_job
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
    mode: str = "print",
    quality: str | None = None,
    clean: bool | None = None,
    print_doc_type: str | None = None,
    ocr_combination: str | None = None,
    publication_year: int | None = None,
    print_language: str | None = None,
    fingerprint: bool = False,
    extract_figures: bool | None = None,
    deskew: bool | None = None,
    fast: bool = False,
    rules_only: bool = False,
    low_latency: bool = False,
    symbol_filter: bool | None = None,
    glyph_heatmap: bool | None = None,
    review_conf_threshold: float | None = None,
    overlaid_ocr: bool | None = None,
    log_fn: Callable[[str], None] | None = None,
    **_: object,
) -> JobManifest:
    s = settings or Settings()
    tier_name = (quality or s.default_quality or DEFAULT_QUALITY_TIER)  # type: ignore[assignment]
    _, tier_flags = resolve_run_flags(
        quality=tier_name,
        fast=fast,
        rules_only=rules_only,
        low_latency=low_latency,
    )
    if tier_flags.get("low_latency"):
        s = apply_low_latency_presets(s)
    elif tier_flags.get("fast"):
        s = apply_fast_presets(s)
    else:
        api_key = s.google_api_key or s.anthropic_api_key or s.openai_api_key
        s = apply_tier_for_run(s, tier_name, api_key=api_key)
    updates: dict = {}
    if clean is not None:
        updates["clean_print"] = clean
    if symbol_filter is not None:
        updates["symbol_filter"] = symbol_filter
    if glyph_heatmap is not None:
        updates["symbol_glyph_heatmap"] = glyph_heatmap
    if review_conf_threshold is not None:
        updates["review_conf_threshold"] = float(review_conf_threshold)
    if print_doc_type:
        updates["print_doc_type"] = print_doc_type
    if ocr_combination:
        updates["ocr_combination"] = ocr_combination
    if publication_year is not None:
        updates["publication_year"] = publication_year
    if print_language:
        updates["print_language"] = print_language
    if fingerprint:
        updates["fingerprint_enabled"] = True
    if extract_figures is not None:
        updates["figure_extract_enabled"] = extract_figures
    if deskew is not None:
        updates["deskew_enabled"] = deskew
    if overlaid_ocr is not None:
        updates["overlaid_ocr_enabled"] = overlaid_ocr
    if updates:
        s = s.model_copy(update=updates)
    job = JobPaths((s.jobs_dir / job_id).expanduser().resolve())
    job.ensure()

    manifest = JobManifest(
        job_id=job_id,
        material_mode="print",
        publication_year=s.publication_year or publication_year,
        print_language=print_language if print_language is not None else s.print_language,
    )

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    if mode not in ("print",):
        _log(f"note: --mode {mode} ignored (print-only)")

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
    if s.fingerprint_enabled and pdf_sources:
        from historical_ocr.backends import fingerprint as fp_backend

        if fp_backend.available():
            scan_out = job.fingerprint
            try:
                fp_backend.scan_pdf(pdf_sources[0], scan_out, dpi=300, seg_dpi=200)
                if s.deskew_enabled:
                    try:
                        n = fp_backend.deskew_scan_pages(scan_out)
                        if n:
                            _log(f"deskew: {n} fingerprint page(s) corrected")
                    except Exception as deskew_exc:
                        _log(f"deskew: fingerprint pages skipped — {deskew_exc}")
                summary = fp_backend.load_summary(scan_out)
                if summary:
                    manifest.fingerprint = summary
                    _log(f"fingerprint: {len(summary.type_case_matches)} type-case match(es)")
            except Exception as exc:
                _log(f"fingerprint: skipped — {exc}")
        else:
            _log("fingerprint: manuscript-fingerprint not on PATH — using image type probes")
    if pdf_sources and s.pdf_density_ocr:
        from historical_ocr.lib.print_ocr import save_pdf_density_artifact

        out = job.artifacts / f"{pdf_sources[0].stem}_density.png"
        if save_pdf_density_artifact(pdf_sources[0], out):
            _log(f"artifact: {out.relative_to(job.root)}")

    resolved = apply_routes(manifest, "print", job_root=job.root, settings=s, log_fn=_log)
    manifest.resolved_material = resolved  # type: ignore[assignment]

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
