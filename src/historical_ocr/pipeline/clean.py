"""Post-OCR normalization with Ted Underwood rules (ocr-cleanup)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.backends import ocr_cleanup as underwood
from historical_ocr.config import JobPaths, Settings
from historical_ocr.lib.rules_only import apply_user_tune_rules, post_clean_sanitize
from historical_ocr.lib.layout_export import export_layout_artifacts, layout_from_clean_text
from historical_ocr.lib.layout_ocr import write_layout_json
from historical_ocr.models.manifest import JobManifest, PageRecord
from historical_ocr.pipeline.paths import page_layout_json, page_pagexml, page_tei


def clean_print_pages(
    pages: list[PageRecord],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    if not settings.clean_print:
        return
    if not underwood.available():
        if log_fn:
            log_fn("warn: ocr-cleanup not available — skipping Underwood clean pass")
        return

    job.ensure()

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    for page in pages:
        if page.route != "print" or page.status != "ok":
            continue
        if not page.ocr_text_path:
            continue

        raw_path = job.root / page.ocr_text_path
        raw = raw_path.read_text(encoding="utf-8")
        _log(f"clean: {page.page_id} (Underwood rules)")

        llm = settings.clean_llm
        if llm and str(llm).lower() in ("none", "off", "false", "0"):
            llm = None

        if page.layout_path and not settings.damage_llm_enabled:
            from historical_ocr.lib.layout_ocr import read_layout_json
            from historical_ocr.lib.confidence_escalation import should_escalate_to_llm_clean

            layout_path = job.root / page.layout_path
            if layout_path.is_file():
                layout = read_layout_json(layout_path)
                decision = should_escalate_to_llm_clean(layout, settings)
                if decision.escalate and not llm:
                    if settings.google_api_key:
                        llm = "gemini"
                    elif settings.anthropic_api_key:
                        llm = "anthropic"
                    if llm:
                        _log(f"escalate: {page.page_id} — {decision.reason} → {llm} clean")

        cleaned = underwood.clean_text(
            raw,
            apply_variants=settings.clean_apply_variants,
            rejoin_linebreaks=settings.clean_rejoin_linebreaks,
            apply_corrections=settings.clean_apply_corrections,
            llm=llm,
            model=settings.clean_llm_model,
            anthropic_api_key=settings.anthropic_api_key,
            google_api_key=settings.google_api_key,
            openai_api_key=settings.openai_api_key,
        )
        cleaned = post_clean_sanitize(cleaned, settings)
        cleaned = apply_user_tune_rules(cleaned, settings)

        out = job.page_artifacts(page.page_id) / "clean.txt"
        out.write_text(cleaned + "\n", encoding="utf-8")
        page.clean_text_path = str(out.relative_to(job.root))

        if not settings.save_layout_artifacts:
            continue

        layout_path = page_layout_json(job.root, page.page_id)
        layout = layout_from_clean_text(layout_path, cleaned)
        if layout is not None:
            write_layout_json(layout, layout_path)
            export_layout_artifacts(
                page.page_id,
                Path(page.image_path).name,
                layout,
                pagexml_path=page_pagexml(job.root, page.page_id),
                tei_path=page_tei(job.root, page.page_id),
                clean_txt_path=out,
            )
            page.pagexml_path = str(page_pagexml(job.root, page.page_id).relative_to(job.root))
            page.tei_path = str(page_tei(job.root, page.page_id).relative_to(job.root))
