"""Print OCR combination planner (mirrors transcription-shell htr/selector.py)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.lib.layout_ocr import LayoutOcrResult

PrintOcrBackend = Literal["tesseract", "pdf_text"]


class PrintPlanKind(str, Enum):
    TESSERACT_ONLY = "tesseract_only"
    PDF_TEXT_FIRST = "pdf_text_first"
    TESSERACT_THEN_CLEAN = "tesseract_then_clean"


@dataclass(frozen=True)
class PrintExecutionPlan:
    kind: PrintPlanKind
    backends: tuple[PrintOcrBackend, ...]
    run_clean: bool = True
    spec: PrintDocumentTypeSpec | None = None


def _effective_combination(settings: Settings, spec: PrintDocumentTypeSpec | None) -> str:
    raw = (settings.ocr_combination or "").strip().lower()
    if not raw and spec:
        raw = spec.ocr_combination.lower()
    if not raw:
        return "tesseract_then_clean"
    aliases = {
        "default": "tesseract_then_clean",
        "ocr_only": "tesseract_only",
        "clean": "tesseract_then_clean",
        "underwood": "tesseract_then_clean",
        "shell": "tesseract_then_clean",
        "shell_print": "tesseract_then_clean",
        "transcription_shell": "tesseract_then_clean",
    }
    return aliases.get(raw, raw)


def plan_print_execution(
    settings: Settings,
    spec: PrintDocumentTypeSpec | None,
    *,
    pdf_available: bool,
) -> PrintExecutionPlan:
    combo = _effective_combination(settings, spec)

    if combo == "pdf_text_first" and pdf_available:
        return PrintExecutionPlan(
            kind=PrintPlanKind.PDF_TEXT_FIRST,
            backends=("pdf_text", "tesseract"),
            run_clean=settings.clean_print,
            spec=spec,
        )

    if combo == "tesseract_only":
        return PrintExecutionPlan(
            kind=PrintPlanKind.TESSERACT_ONLY,
            backends=("tesseract",),
            run_clean=False,
            spec=spec,
        )

    return PrintExecutionPlan(
        kind=PrintPlanKind.TESSERACT_THEN_CLEAN,
        backends=("tesseract",),
        run_clean=settings.clean_print,
        spec=spec,
    )


def run_tesseract_backend(
    image: Path,
    *,
    lang: str,
    psm: int,
    preprocess: dict,
    settings=None,
    print_spec: PrintDocumentTypeSpec | None = None,
    ink_layout=None,
    log_fn=None,
) -> LayoutOcrResult:
    from historical_ocr.lib.layout_ocr import ocr_image_text_only, ocr_image_with_layout
    from historical_ocr.lib.ocr_confusables import apply_confusables_to_result
    from historical_ocr.lib.symbol_filter import resolve_symbol_filter
    from historical_ocr.ocr.preprocess import preprocess_for_ocr

    filter_opts = resolve_symbol_filter(settings, print_spec) if settings else None
    use_layout = settings is None or getattr(settings, "save_layout_artifacts", True)
    ocr_fn = ocr_image_with_layout if use_layout else ocr_image_text_only
    tei_section_ocr = bool(print_spec and print_spec.tei_section_ocr and use_layout)
    column_ocr = bool(print_spec and print_spec.column_ocr and use_layout)
    section_psm = print_spec.tei_section_psm if print_spec else 6
    section_gap = print_spec.tei_section_min_gap_px if print_spec else 18
    column_psm = print_spec.column_ocr_psm if print_spec else 6
    column_gutter = print_spec.column_ocr_min_gutter_px if print_spec else 14

    def _finish(result: LayoutOcrResult) -> LayoutOcrResult:
        return apply_confusables_to_result(result)

    def _ink_multi_column() -> bool:
        return ink_layout is not None and len(ink_layout.columns) >= 2

    def _run(path: Path) -> LayoutOcrResult:
        # Priority: ink-zone overlaid → column OCR → TEI sections → full page.
        if (
            getattr(settings, "overlaid_ocr_enabled", False)
            and ink_layout is not None
            and use_layout
        ):
            from historical_ocr.lib.overlaid_ocr import ocr_image_overlaid

            use_sections = len(ink_layout.sections) >= 2 and not _ink_multi_column()
            overlaid_result = ocr_image_overlaid(
                path,
                ink_layout,
                lang=lang,
                psm=column_psm if _ink_multi_column() else section_psm,
                settings=settings,
                filter_opts=filter_opts,
                use_sections=use_sections,
                log_fn=log_fn,
            )
            if overlaid_result is not None:
                return _finish(overlaid_result)

        if column_ocr and _ink_multi_column():
            from historical_ocr.lib.column_ocr import ocr_image_by_columns

            column_result = ocr_image_by_columns(
                path,
                lang=lang,
                psm=column_psm,
                settings=settings,
                filter_opts=filter_opts,
                min_gutter_px=column_gutter,
                ink_layout=ink_layout,
                log_fn=log_fn,
            )
            if column_result is not None:
                return _finish(column_result)

        if tei_section_ocr:
            from historical_ocr.lib.tei_sectioning import ocr_image_by_tei_sections

            section_result = ocr_image_by_tei_sections(
                path,
                lang=lang,
                psm=section_psm,
                settings=settings,
                filter_opts=filter_opts,
                min_gutter_px=column_gutter,
                min_gap_px=section_gap,
                log_fn=log_fn,
            )
            if section_result is not None:
                return _finish(section_result)

        if column_ocr:
            from historical_ocr.lib.column_ocr import ocr_image_by_columns

            column_result = ocr_image_by_columns(
                path,
                lang=lang,
                psm=column_psm,
                settings=settings,
                filter_opts=filter_opts,
                min_gutter_px=column_gutter,
                ink_layout=ink_layout,
                log_fn=log_fn,
            )
            if column_result is not None:
                return _finish(column_result)
        return _finish(
            ocr_fn(
                path,
                lang=lang,
                psm=psm,
                settings=settings,
                filter_opts=filter_opts,
            ),
        )

    if preprocess:
        import tempfile

        processed = preprocess_for_ocr(image, preprocess)
        tmp = Path(tempfile.mkdtemp()) / f"{image.stem}_prep.jpg"
        processed.save(tmp, format="JPEG", quality=92)
        try:
            return _run(tmp)
        finally:
            tmp.unlink(missing_ok=True)
    return _run(image)
