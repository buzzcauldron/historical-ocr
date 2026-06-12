"""Orthogonal print-page stages: ink prep → OCR → post-process."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.lib.handwriting_detect import (
    HandwritingAssessment,
    apply_handwriting_hint,
    assess_handwriting,
)
from historical_ocr.lib.ink_layout import InkLayout
from historical_ocr.lib.layout_ocr import LayoutOcrResult
from historical_ocr.models.manifest import JobManifest, PageRecord


@dataclass
class PageProcessCounts:
    ink_columns: int = 0
    ink_sections: int = 0
    ocr_lines: int = 0
    mean_conf: float | None = None
    damage_retries: int = 0
    trocr_repairs: int = 0
    damage_llm_repairs: int = 0
    handwriting_gemini: int = 0
    handwriting_extent: str = "none"
    ink_s: float = 0.0
    ocr_s: float = 0.0
    post_s: float = 0.0
    elapsed_s: float = 0.0
    extra: dict[str, int] = field(default_factory=dict)

    def absorb(self, other: PageProcessCounts) -> None:
        """Merge ink-prep counts into this post-process summary."""
        if other.ink_columns:
            self.ink_columns = other.ink_columns
        if other.ink_sections:
            self.ink_sections = other.ink_sections
        self.extra.update(other.extra)

    def summary_line(self, page_id: str) -> str:
        conf = f"{self.mean_conf:.1f}" if self.mean_conf is not None else "—"
        parts = [
            f"page={page_id}",
            f"{self.elapsed_s:.1f}s",
            f"lines={self.ocr_lines}",
            f"conf={conf}",
        ]
        if self.ink_sections:
            parts.append(f"ink={self.ink_columns}c/{self.ink_sections}s")
        if self.ink_s or self.ocr_s or self.post_s:
            parts.append(
                f"time=ink:{self.ink_s:.1f}s ocr:{self.ocr_s:.1f}s post:{self.post_s:.1f}s",
            )
        if self.damage_retries:
            parts.append(f"dmg-retry={self.damage_retries}")
        if self.trocr_repairs:
            parts.append(f"trocr={self.trocr_repairs}")
        if self.damage_llm_repairs:
            parts.append(f"dmg-llm={self.damage_llm_repairs}")
        if self.handwriting_gemini:
            parts.append(f"hw-gemini={self.handwriting_gemini}")
        if self.handwriting_extent != "none":
            parts.append(f"hw={self.handwriting_extent}")
        return "page-stats: " + " ".join(parts)


def layout_section_params(spec: PrintDocumentTypeSpec | None) -> tuple[int, int]:
    if spec is None:
        return 14, 18
    return spec.column_ocr_min_gutter_px, spec.tei_section_min_gap_px


def prepare_ink_layout(
    job_root: Path,
    page_id: str,
    image: Path,
    settings: Settings,
    spec: PrintDocumentTypeSpec | None,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[PageProcessCounts, InkLayout | None]:
    counts = PageProcessCounts()
    if not settings.save_layout_artifacts:
        return counts, None

    from historical_ocr.lib.ink_layout import analyze_ink_layout_image, persist_ink_layout, render_ink_layout_heatmap
    from historical_ocr.pipeline.paths import page_ink_layout_png

    gutter, gap = layout_section_params(spec)
    ink = analyze_ink_layout_image(image, min_gutter_px=gutter, min_gap_px=gap)
    if ink is None:
        return counts, None

    counts.ink_columns = len(ink.columns)
    counts.ink_sections = len(ink.sections)
    persist_ink_layout(job_root, page_id, ink)
    multi = "multi-column" if counts.ink_columns >= 2 else "single-column"
    if log_fn:
        log_fn(
            f"ink-layout: {counts.ink_columns} column(s) [{multi}], "
            f"{counts.ink_sections} section(s) on {page_id}",
        )
    if settings.symbol_glyph_heatmap and (counts.ink_columns >= 2 or counts.ink_sections >= 2):
        render_ink_layout_heatmap(image, page_ink_layout_png(job_root, page_id), ink)
    return counts, ink


def postprocess_layout(
    layout: LayoutOcrResult,
    image: Path,
    settings: Settings,
    spec: PrintDocumentTypeSpec | None,
    page: PageRecord,
    manifest: JobManifest | None,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[LayoutOcrResult, PageProcessCounts]:
    counts = PageProcessCounts()
    lang = spec.tesseract_lang if spec else settings.tesseract_lang

    if settings.damage_retry_enabled and layout.lines:
        from historical_ocr.lib.damage_retry import retry_weak_lines

        weak_before = sum(1 for ln in layout.lines if ln.conf < settings.damage_retry_conf_threshold)
        layout = retry_weak_lines(layout, image, lang=lang, settings=settings, log_fn=log_fn)
        weak_after = sum(1 for ln in layout.lines if ln.conf < settings.damage_retry_conf_threshold)
        counts.damage_retries = max(0, weak_before - weak_after)

    if getattr(settings, "trocr_enabled", False) and layout.lines:
        from historical_ocr.lib.trocr_retry import retry_weak_lines_with_trocr

        weak_before = sum(1 for ln in layout.lines if ln.conf < settings.trocr_conf_threshold)
        layout = retry_weak_lines_with_trocr(layout, image, settings=settings, log_fn=log_fn)
        weak_after = sum(1 for ln in layout.lines if ln.conf < settings.trocr_conf_threshold)
        counts.trocr_repairs = max(0, weak_before - weak_after)

    if settings.damage_llm_enabled and layout.lines:
        from historical_ocr.lib.damage_llm import repair_weak_lines_with_llm

        weak_before = sum(1 for ln in layout.lines if ln.conf < settings.damage_llm_conf_threshold)
        layout = repair_weak_lines_with_llm(layout, settings=settings, log_fn=log_fn)
        weak_after = sum(1 for ln in layout.lines if ln.conf < settings.damage_llm_conf_threshold)
        counts.damage_llm_repairs = max(0, weak_before - weak_after)

    if manifest is not None and getattr(settings, "handwriting_detect_enabled", True):
        from historical_ocr.lib.handwriting_gemini import transcribe_partial_handwriting

        hw: HandwritingAssessment = assess_handwriting(
            image,
            layout=layout,
            fingerprint=manifest.fingerprint,
        )
        counts.handwriting_extent = hw.extent
        if hw.extent == "partial":
            before_lines = {ln.line_num: ln.text for ln in layout.lines}
            layout = transcribe_partial_handwriting(
                layout,
                image,
                hw,
                settings=settings,
                log_fn=log_fn,
            )
            counts.handwriting_gemini = sum(
                1 for ln in layout.lines if before_lines.get(ln.line_num) != ln.text
            )
        apply_handwriting_hint(page, manifest, image, hw, log_fn=log_fn)

    if layout.lines:
        counts.ocr_lines = len([ln for ln in layout.lines if ln.text.strip()])
        confs = [ln.conf for ln in layout.lines if ln.conf >= 0]
        if confs:
            counts.mean_conf = sum(confs) / len(confs)

    return layout, counts


def timed_page_process(
    fn: Callable[[], tuple[LayoutOcrResult, PageProcessCounts]],
) -> tuple[LayoutOcrResult, PageProcessCounts]:
    t0 = time.perf_counter()
    layout, counts = fn()
    counts.elapsed_s = time.perf_counter() - t0
    return layout, counts
