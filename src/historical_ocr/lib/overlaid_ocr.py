"""Ink-zone overlaid OCR — OCR per heatmap column/section region."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.lib.ink_layout import InkLayout
from historical_ocr.lib.layout_ocr import LayoutOcrResult, TeiSection
from historical_ocr.lib.region_ocr import RegionBox, ocr_image_regions

__all__ = ["ocr_image_overlaid", "regions_from_ink_layout"]


def regions_from_ink_layout(
    layout: InkLayout,
    *,
    use_sections: bool = True,
    pad: int = 4,
) -> list[RegionBox]:
    """Build OCR regions from ink-layout columns or horizontal bands."""
    if len(layout.columns) >= 2:
        return [
            RegionBox(
                left=col.left,
                top=0,
                width=col.width,
                height=layout.page_height,
                sort_col=col.index,
                pad=pad,
            )
            for col in layout.columns
        ]

    if use_sections and len(layout.sections) >= 2:
        return [
            RegionBox(
                left=sec.left,
                top=sec.top,
                width=sec.width,
                height=sec.height,
                sort_col=sec.column_index,
                sort_band=sec.top,
                section_id=sec.section_id,
                pad=pad,
            )
            for sec in layout.sections
        ]

    return []


def _tei_sections_from_layout(layout: InkLayout) -> tuple[TeiSection, ...]:
    return tuple(
        TeiSection(
            section_id=sec.section_id,
            section_type="section",
            left=sec.left,
            top=sec.top,
            width=sec.width,
            height=sec.height,
            column_index=sec.column_index,
        )
        for sec in layout.sections
    )


def ocr_image_overlaid(
    image: Path,
    ink_layout: InkLayout,
    *,
    lang: str,
    psm: int,
    settings=None,
    filter_opts=None,
    use_sections: bool = True,
    region_pad_px: int = 4,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult | None:
    """OCR ink-zone overlays (columns or section bands) with merged reading order."""
    regions = regions_from_ink_layout(
        ink_layout,
        use_sections=use_sections,
        pad=region_pad_px,
    )
    if len(regions) < 2:
        return None

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    kind = "column" if len(ink_layout.columns) >= 2 else "section"
    _log(
        f"overlaid-ocr: {len(regions)} {kind} zone(s), "
        f"{len(ink_layout.columns)} column(s) on {image.name}",
    )

    sections = _tei_sections_from_layout(ink_layout) if use_sections else ()
    result = ocr_image_regions(
        image,
        regions,
        lang=lang,
        psm=psm,
        settings=settings,
        filter_opts=filter_opts,
        log_label="overlaid-ocr",
        log_fn=log_fn,
    )
    if result is None:
        return None

    return LayoutOcrResult(
        lines=result.lines,
        page_width=result.page_width,
        page_height=result.page_height,
        full_text=result.full_text,
        sections=sections or result.sections,
    )
