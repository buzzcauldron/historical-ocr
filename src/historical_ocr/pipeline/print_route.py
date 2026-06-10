"""Diachronic print OCR with doc_type forking (transcription-shell pattern)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.backends import transcriber_shell as shell
from historical_ocr.config import JobPaths, Settings
from historical_ocr.document_types.language_overlay import apply_language_overlay
from historical_ocr.document_types.print_types import (
    PrintDocumentTypeSpec,
    apply_print_doc_type,
    load_print_doc_type,
    suggest_print_doc_type,
)
from historical_ocr.lib.layout_export import export_layout_artifacts
from historical_ocr.lib.layout_ocr import LayoutOcrResult, write_layout_json
from historical_ocr.lib.print_ocr import extract_pdf_page_text
from historical_ocr.models.manifest import JobManifest, PageRecord
from historical_ocr.pipeline.paths import page_layout_json, page_pagexml, page_tei
from historical_ocr.pipeline.print_selector import (
    PrintPlanKind,
    plan_print_execution,
    run_tesseract_backend,
)


def resolve_print_spec(settings: Settings, manifest: JobManifest) -> PrintDocumentTypeSpec:
    language = settings.print_language or manifest.print_language
    name = settings.print_doc_type or manifest.print_doc_type or "auto"
    if name == "auto":
        name = suggest_print_doc_type(
            manifest=manifest,
            language=language,
            fingerprint_era=getattr(manifest.fingerprint, "suggested_material", None),
        )
    spec = load_print_doc_type(name)
    return apply_language_overlay(spec, language)


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
    source_pdf: Path | None = None,
    prompt_path: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    image = job.root / page.image_path
    spec = print_spec
    if spec:
        page.print_doc_type = spec.name
        settings = apply_print_doc_type(settings, spec)

    plan = plan_print_execution(
        settings,
        spec,
        shell_available=shell.available(),
        pdf_available=bool(source_pdf and source_pdf.is_file()),
    )
    _log(f"print-ocr: {page.page_id} [{plan.kind.value}] doc_type={spec.name if spec else '—'}")

    out_txt = job.ocr / f"{page.page_id}.txt"

    try:
        if plan.kind == PrintPlanKind.SHELL_PRINT and spec and spec.shell_doc_type:
            if not prompt_path or not prompt_path.is_file():
                _log("warn: shell_print needs --prompt; falling back to tesseract")
            else:
                proc = shell.run_print_page(
                    job_id=page.page_id,
                    image=image,
                    prompt=prompt_path,
                    doc_type=spec.shell_doc_type,
                    provider=settings.default_provider,
                    model=settings.default_model,
                    lineation=spec.shell_lineation,  # type: ignore[arg-type]
                    htr_combination=spec.shell_htr_combination,
                    artifacts_dir=job.artifacts,
                )
                if proc.returncode == 0:
                    yaml_path = shell.find_transcription_yaml(job.artifacts, page.page_id, image)
                    if yaml_path and yaml_path.is_file():
                        import yaml

                        from historical_ocr.lib.protocol_text import plain_text_from_yaml_dict

                        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                        text = plain_text_from_yaml_dict(data) if isinstance(data, dict) else ""
                        out_txt.write_text(text + "\n", encoding="utf-8")
                        page.ocr_text_path = str(out_txt.relative_to(job.root))
                        page.transcription_yaml = str(yaml_path.relative_to(job.root))
                        lines_xml = shell.find_lines_xml(job.artifacts, page.page_id)
                        if lines_xml:
                            import shutil

                            pagexml_out = page_pagexml(job.root, page.page_id)
                            pagexml_out.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(lines_xml, pagexml_out)
                            page.pagexml_path = str(pagexml_out.relative_to(job.root))
                        page.status = "ok"
                        return
                err = (proc.stderr or proc.stdout or "shell print failed").strip()
                page.errors.append(err[:300])
                _log(f"warn: shell_print failed — {err[:120]}")

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

        lang = spec.tesseract_lang if spec else settings.tesseract_lang
        psm = spec.tesseract_psm if spec else 6
        preprocess = spec.preprocess if spec else {}
        layout = run_tesseract_backend(
            image,
            lang=lang,
            psm=psm,
            preprocess=preprocess,
            settings=settings,
        )
        out_txt.write_text(layout.full_text + "\n", encoding="utf-8")
        page.ocr_text_path = str(out_txt.relative_to(job.root))
        _save_layout_outputs(page, job, image, layout)
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
    prompt_path: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    job.ensure()
    spec = print_spec or resolve_print_spec(settings, manifest)
    manifest.print_doc_type = spec.name
    manifest.print_ocr_combination = settings.ocr_combination or spec.ocr_combination

    for page in pages:
        if page.route != "print":
            continue
        ocr_single_page(
            page,
            job,
            settings,
            print_spec=spec,
            source_pdf=source_pdf,
            prompt_path=prompt_path,
            log_fn=log_fn,
        )
