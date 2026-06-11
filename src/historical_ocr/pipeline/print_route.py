"""Diachronic print OCR with doc_type forking."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from historical_ocr.config import JobPaths, Settings
from historical_ocr.document_types.language_overlay import apply_language_overlay
from historical_ocr.document_types.print_types import (
    PrintDocumentTypeSpec,
    apply_print_doc_type,
    load_print_doc_type,
)
from historical_ocr.lib.type_routing import doc_type_from_hints, fingerprint_era_hint, page_type_hint
from historical_ocr.lib.layout_export import export_layout_artifacts
from historical_ocr.lib.layout_ocr import LayoutOcrResult, write_layout_json
from historical_ocr.lib.print_ocr import extract_pdf_page_text
from historical_ocr.lib.print_page_process import postprocess_layout, prepare_ink_layout
from historical_ocr.models.manifest import JobManifest, PageRecord
from historical_ocr.pipeline.paths import (
    lines_xml_path,
    page_layout_json,
    page_pagexml,
    page_tei,
    transcription_yaml_path,
)
from historical_ocr.pipeline.print_selector import (
    PrintPlanKind,
    plan_print_execution,
    run_tesseract_backend,
)


def resolve_print_spec(settings: Settings, manifest: JobManifest) -> PrintDocumentTypeSpec:
    language = settings.print_language or manifest.print_language
    name = settings.print_doc_type or manifest.print_doc_type or "auto"
    if name == "auto":
        name = doc_type_from_hints(
            manifest=manifest,
            language=language,
            fingerprint_era=fingerprint_era_hint(manifest.fingerprint),
        )
    spec = load_print_doc_type(name)
    return apply_language_overlay(spec, language)


def resolve_print_spec_for_page(
    settings: Settings,
    manifest: JobManifest,
    image: Path,
    *,
    job_spec: PrintDocumentTypeSpec | None,
) -> PrintDocumentTypeSpec:
    """Per-page doc_type when auto routing is enabled."""
    fixed = settings.print_doc_type or manifest.print_doc_type or "auto"
    if fixed != "auto" or not settings.per_page_type_routing:
        return job_spec or resolve_print_spec(settings, manifest)

    language = settings.print_language or manifest.print_language
    image_era = page_type_hint(image, manifest)
    name = doc_type_from_hints(
        manifest=manifest,
        language=language,
        image_era=image_era,
    )
    spec = load_print_doc_type(name)
    return apply_language_overlay(spec, language)


def _extract_figures_for_page(
    page: PageRecord,
    job: JobPaths,
    image: Path,
    layout: LayoutOcrResult,
    settings: Settings,
    log_fn: Callable[[str], None] | None,
) -> None:
    if not settings.figure_extract_enabled:
        return

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    try:
        from historical_ocr.lib.protocol_yaml import write_transcription_yaml
        from historical_ocr.pipeline.figure_extract import extract_figures_for_page

        art_dir = job.root / "artifacts" / page.page_id
        art_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = transcription_yaml_path(art_dir.parent, page.page_id, image)
        write_transcription_yaml(
            layout,
            yaml_path,
            page_id=page.page_id,
            image_name=image.name,
        )
        page.transcription_yaml = str(yaml_path.relative_to(job.root))

        report = extract_figures_for_page(
            image_path=image,
            lines_xml_path=lines_xml_path(art_dir.parent, page.page_id)
            if lines_xml_path(art_dir.parent, page.page_id).is_file()
            else None,
            transcription_yaml_path=yaml_path,
            settings=settings,
        )
        if report.figures:
            _log(f"figures: {page.page_id} — {len(report.figures)} ({report.backend})")
        elif report.warnings:
            _log(f"figures: {page.page_id} — {report.warnings[0]}")
    except RuntimeError as exc:
        _log(f"figures: {page.page_id} skipped — {exc}")
    except Exception as exc:
        _log(f"figures: {page.page_id} error — {exc}")


def _save_layout_outputs(
    page: PageRecord,
    job: JobPaths,
    image: Path,
    layout: LayoutOcrResult,
) -> None:
    layout_path = page_layout_json(job.root, page.page_id)
    write_layout_json(layout, layout_path)
    page.layout_path = str(layout_path.relative_to(job.root))
    export_layout_artifacts(
        page.page_id,
        image.name,
        layout,
        pagexml_path=page_pagexml(job.root, page.page_id),
        tei_path=page_tei(job.root, page.page_id),
        clean_txt_path=job.ocr / f"{page.page_id}.layout.txt",
    )
    page.pagexml_path = str(page_pagexml(job.root, page.page_id).relative_to(job.root))
    page.tei_path = str(page_tei(job.root, page.page_id).relative_to(job.root))


def _pdf_page_index(page: PageRecord) -> int:
    try:
        return int(page.page_id.rsplit("_p", 1)[-1])
    except ValueError:
        return 0


def ocr_single_page(
    page: PageRecord,
    job: JobPaths,
    settings: Settings,
    *,
    print_spec: PrintDocumentTypeSpec | None,
    manifest: JobManifest | None = None,
    source_pdf: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    image = job.root / page.image_path
    spec = print_spec
    if manifest is not None:
        spec = resolve_print_spec_for_page(settings, manifest, image, job_spec=print_spec)
    if spec:
        page.print_doc_type = spec.name
        settings = apply_print_doc_type(settings, spec)

    plan = plan_print_execution(
        settings,
        spec,
        pdf_available=bool(source_pdf and source_pdf.is_file()),
    )
    _log(f"print-ocr: {page.page_id} [{plan.kind.value}] doc_type={spec.name if spec else '—'}")

    out_txt = job.ocr / f"{page.page_id}.txt"

    try:
        if plan.kind == PrintPlanKind.PDF_TEXT_FIRST and source_pdf and source_pdf.is_file():
            text = extract_pdf_page_text(
                source_pdf,
                _pdf_page_index(page),
                lang=settings.tesseract_lang,
                settings=settings,
            )
            if len(text.strip()) >= 80:
                out_txt.write_text(text + "\n", encoding="utf-8")
                page.ocr_text_path = str(out_txt.relative_to(job.root))
                page.status = "ok"
                return

        t0 = time.perf_counter()
        ink_counts = prepare_ink_layout(
            job.root,
            page.page_id,
            image,
            settings,
            spec,
            log_fn=_log,
        )

        lang = spec.tesseract_lang if spec else settings.tesseract_lang
        psm = spec.tesseract_psm if spec else 6
        preprocess = spec.preprocess if spec else {}
        layout = run_tesseract_backend(
            image,
            lang=lang,
            psm=psm,
            preprocess=preprocess,
            settings=settings,
            print_spec=spec,
            log_fn=_log,
        )
        layout, counts = postprocess_layout(
            layout,
            image,
            settings,
            spec,
            page,
            manifest,
            log_fn=_log,
        )
        counts.absorb(ink_counts)
        counts.elapsed_s = time.perf_counter() - t0
        _log(counts.summary_line(page.page_id))
        out_txt.write_text(layout.full_text + "\n", encoding="utf-8")
        page.ocr_text_path = str(out_txt.relative_to(job.root))
        if settings.save_layout_artifacts:
            _save_layout_outputs(page, job, image, layout)
        _extract_figures_for_page(page, job, image, layout, settings, _log)
        page.status = "ok"
    except Exception as e:
        page.status = "error"
        page.errors.append(str(e))


def ocr_pages(
    pages: list[PageRecord],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
    *,
    source_pdf: Path | None = None,
    print_spec: PrintDocumentTypeSpec | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    job.ensure()
    spec = print_spec or resolve_print_spec(settings, manifest)
    manifest.print_doc_type = spec.name
    manifest.print_ocr_combination = settings.ocr_combination or spec.ocr_combination

    targets = [p for p in pages if p.route == "print"]
    workers = max(1, int(settings.parallel_pages))

    def _run_one(page: PageRecord) -> None:
        ocr_single_page(
            page,
            job,
            settings,
            print_spec=spec,
            manifest=manifest,
            source_pdf=source_pdf,
            log_fn=log_fn,
        )

    if workers == 1 or len(targets) <= 1:
        for page in targets:
            _run_one(page)
        return

    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
        futures = {pool.submit(_run_one, page): page for page in targets}
        for fut in as_completed(futures):
            fut.result()
