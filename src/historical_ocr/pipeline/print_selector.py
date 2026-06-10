"""Print OCR combination planner (mirrors transcription-shell htr/selector.py)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.lib.layout_ocr import LayoutOcrResult

PrintOcrBackend = Literal["tesseract", "pdf_text", "shell"]


class PrintPlanKind(str, Enum):
    TESSERACT_ONLY = "tesseract_only"
    PDF_TEXT_FIRST = "pdf_text_first"
    TESSERACT_THEN_CLEAN = "tesseract_then_clean"
    SHELL_PRINT = "shell_print"


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
        "shell": "shell_print",
        "transcription_shell": "shell_print",
    }
    return aliases.get(raw, raw)


def plan_print_execution(
    settings: Settings,
    spec: PrintDocumentTypeSpec | None,
    *,
    shell_available: bool,
    pdf_available: bool,
) -> PrintExecutionPlan:
    combo = _effective_combination(settings, spec)

    if combo == "shell_print":
        if shell_available and spec and spec.shell_doc_type:
            return PrintExecutionPlan(
                kind=PrintPlanKind.SHELL_PRINT,
                backends=("shell",),
                run_clean=False,
                spec=spec,
            )
        combo = "tesseract_then_clean"

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
) -> LayoutOcrResult:
    from historical_ocr.lib.layout_ocr import ocr_image_text_only, ocr_image_with_layout
    from historical_ocr.lib.symbol_filter import resolve_symbol_filter
    from historical_ocr.ocr.preprocess import preprocess_for_ocr

    filter_opts = resolve_symbol_filter(settings, print_spec) if settings else None
    use_layout = settings is None or getattr(settings, "save_layout_artifacts", True)
    ocr_fn = ocr_image_with_layout if use_layout else ocr_image_text_only

    def _run(path: Path) -> LayoutOcrResult:
        return ocr_fn(
            path,
            lang=lang,
            psm=psm,
            settings=settings,
            filter_opts=filter_opts,
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
