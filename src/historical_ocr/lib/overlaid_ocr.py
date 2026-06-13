"""Ink-zone overlaid OCR — OCR per heatmap column/section region."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.lib.ink_layout import InkLayout, detect_column_bounds
from historical_ocr.lib.layout_ocr import LayoutOcrResult, TeiSection
from historical_ocr.lib.region_ocr import RegionBox, ocr_image_regions
from historical_ocr.lib.text_section_filter import filter_text_regions, summarize_skipped

__all__ = ["ocr_image_overlaid", "regions_from_ink_layout", "expand_wide_regions"]


def _sections_per_column(layout: InkLayout) -> dict[int, tuple[InkSection, ...]]:
    by_col: dict[int, list[InkSection]] = {}
    for sec in layout.sections:
        by_col.setdefault(sec.column_index, []).append(sec)
    return {col: tuple(secs) for col, secs in by_col.items()}


def _use_section_bands_for_columns(layout: InkLayout) -> bool:
    """Many ink bands per column → section crops; simple pages keep full-height columns."""
    n_cols = len(layout.columns)
    if n_cols < 2 or not layout.sections:
        return False
    return len(layout.sections) > n_cols * 2


def _separate_banner_regions(
    regions: list[RegionBox],
    page_width: int,
    page_height: int,
    n_cols: int,
    *,
    max_top_align_px: int = 60,
    min_span_frac: float = 0.70,
    min_sliver_px: int = 20,
) -> tuple[list[RegionBox], list[RegionBox]]:
    """Split full-width banner zones from column-local sections.

    When the topmost section in each column starts at nearly the same y-position
    and together they span most of the page width, the overlap band is likely a
    multi-column headline or masthead.  Replace those individual column strips
    with a single full-width crop so Tesseract sees the complete text rather than
    a truncated fragment in each column.

    Returns (banner_regions, remaining_column_regions).
    """
    if n_cols < 2 or not regions:
        return [], regions

    by_col: dict[int, list[RegionBox]] = {}
    for r in regions:
        by_col.setdefault(r.sort_col, []).append(r)

    if len(by_col) < max(2, n_cols - 1):
        return [], regions

    top_per_col: dict[int, RegionBox] = {
        col: min(secs, key=lambda r: r.top) for col, secs in by_col.items()
    }
    top_secs = list(top_per_col.values())

    tops = [s.top for s in top_secs]
    if max(tops) - min(tops) > max_top_align_px:
        return [], regions

    x_min = min(s.left for s in top_secs)
    x_max = max(s.left + s.width for s in top_secs)
    if x_max - x_min < page_width * min_span_frac:
        return [], regions

    # Banner zone: from the common top to the earliest section bottom.
    banner_top = min(tops)
    banner_bot = min(s.top + s.height for s in top_secs)
    if banner_bot <= banner_top:
        return [], regions

    pad = regions[0].pad if regions else 4
    banner = RegionBox(
        left=x_min,
        top=banner_top,
        width=x_max - x_min,
        height=banner_bot - banner_top,
        sort_col=-1,
        sort_band=banner_top,
        pad=pad,
    )

    top_ids = {id(r) for r in top_secs}
    col_regions: list[RegionBox] = []
    for r in regions:
        if id(r) in top_ids:
            new_top = banner_bot
            remaining_h = (r.top + r.height) - new_top
            if remaining_h > min_sliver_px:
                col_regions.append(RegionBox(
                    left=r.left,
                    top=new_top,
                    width=r.width,
                    height=remaining_h,
                    sort_col=r.sort_col,
                    sort_subcol=r.sort_subcol,
                    sort_band=new_top,
                    section_id=r.section_id,
                    pad=r.pad,
                ))
        else:
            col_regions.append(r)

    return [banner], col_regions


def _narrowest_column_width(layout: InkLayout) -> int:
    widths = [col.width for col in layout.columns]
    return min(widths) if widths else 0


def _refine_sub_bounds(
    bounds: list[tuple[int, int]],
    crop_w: int,
    narrow_w: int,
) -> list[tuple[int, int]]:
    """When ink detection leaves one very wide column, bisect for parallel newspaper text."""
    if len(bounds) < 2:
        return bounds
    widths = [x1 - x0 for x0, x1 in bounds]
    if max(widths) <= crop_w * 0.55:
        return bounds
    mid = crop_w // 2
    min_part = int(narrow_w * 0.25)
    if mid >= min_part and (crop_w - mid) >= min_part:
        return [(0, mid), (mid, crop_w)]
    return bounds


def expand_wide_regions(
    image: Path,
    regions: list[RegionBox],
    layout: InkLayout,
) -> list[RegionBox]:
    """Split OCR regions wider than ~1.5× the narrowest column at ink gutters."""
    narrow_w = _narrowest_column_width(layout)
    if narrow_w <= 0 or len(layout.columns) < 2:
        return regions

    threshold = int(narrow_w * 1.2)

    from PIL import Image

    with Image.open(image) as im:
        gray = im.convert("L")
        page_w, page_h = im.size

        def _split_one(region: RegionBox) -> list[RegionBox]:
            if region.width <= threshold:
                return [region]

            x0 = region.left
            y0 = region.top
            x1 = min(page_w, region.left + region.width)
            y1 = min(page_h, region.top + region.height)
            crop = gray.crop((x0, y0, x1, y1))
            sub_bounds = detect_column_bounds(crop)
            if len(sub_bounds) < 2:
                return [region]
            sub_bounds = _refine_sub_bounds(sub_bounds, crop.size[0], narrow_w)

            sub_regions: list[RegionBox] = []
            for sub_i, (sx0, sx1) in enumerate(sub_bounds):
                sub_w = sx1 - sx0
                if sub_w < int(narrow_w * 0.25):
                    continue
                sub_regions.append(
                    RegionBox(
                        left=x0 + sx0,
                        top=region.top,
                        width=sub_w,
                        height=region.height,
                        sort_col=region.sort_col,
                        sort_subcol=x0 + sx0,
                        sort_band=region.sort_band,
                        section_id=region.section_id,
                        pad=region.pad,
                    ),
                )
            return sub_regions if len(sub_regions) >= 2 else [region]

        expanded: list[RegionBox] = []
        for region in regions:
            expanded.extend(_split_one(region))

        # Re-split any sub-regions that remain wider than the threshold.
        changed = True
        while changed:
            changed = False
            next_pass: list[RegionBox] = []
            for region in expanded:
                parts = _split_one(region)
                if len(parts) > 1:
                    changed = True
                next_pass.extend(parts)
            expanded = next_pass

    return expanded if len(expanded) >= 2 else regions


def regions_from_ink_layout(
    layout: InkLayout,
    *,
    use_sections: bool = True,
    pad: int = 4,
) -> list[RegionBox]:
    """Build OCR regions from ink-layout columns or horizontal bands."""
    if len(layout.columns) >= 2:
        if _use_section_bands_for_columns(layout):
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

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    using_section_bands = _use_section_bands_for_columns(ink_layout) or (
        len(ink_layout.columns) < 2 and use_sections
    )
    regions = regions_from_ink_layout(
        ink_layout,
        use_sections=use_sections,
        pad=region_pad_px,
    )
    regions = expand_wide_regions(image, regions, ink_layout)

    # When using section bands on a multi-column layout, detect full-width
    # banner zones (mastheads, spanning headlines).  These are OCR'd as a
    # single wide crop so Tesseract sees the complete text instead of a
    # truncated fragment in each column.
    banner_regions: list[RegionBox] = []
    if using_section_bands and len(ink_layout.columns) >= 2:
        banner_regions, regions = _separate_banner_regions(
            regions,
            ink_layout.page_width,
            ink_layout.page_height,
            n_cols=len(ink_layout.columns),
        )
        if banner_regions:
            _log(
                f"banner-ocr: {len(banner_regions)} full-width zone(s) "
                f"separated from column bands",
            )

    # Only apply text-slice filtering on section bands, not full-height column
    # crops — filtering a full column would drop it entirely and fall back to
    # full-page OCR which merges lines across columns.
    if using_section_bands:
        kept, skipped = filter_text_regions(image, regions, settings=settings)
        if skipped:
            _log(
                f"text-slice: kept {len(kept)}/{len(regions)} regions"
                f" (skipped {summarize_skipped(skipped)})",
            )
        regions = kept

    all_regions = banner_regions + regions
    if len(all_regions) < 2:
        return None

    if len(ink_layout.columns) >= 2 and not _use_section_bands_for_columns(ink_layout):
        kind = "column"
    else:
        kind = "section"
    _log(
        f"overlaid-ocr: {len(all_regions)} {kind} zone(s), "
        f"{len(ink_layout.columns)} column(s) on {image.name}",
    )

    sections = _tei_sections_from_layout(ink_layout) if use_sections else ()
    result = ocr_image_regions(
        image,
        all_regions,
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
