"""Crop-and-OCR for page regions (columns, TEI sections)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine


@dataclass(frozen=True)
class RegionBox:
    left: int
    top: int
    width: int
    height: int
    sort_col: int = 0
    sort_subcol: int = 0
    sort_band: int = 0
    section_id: int | None = None
    pad: int = 4


def merge_region_results(
    results: list[tuple[RegionBox, LayoutOcrResult]],
    *,
    page_width: int,
    page_height: int,
    sections: tuple = (),
    crop_origins: list[tuple[int, int]] | None = None,
) -> LayoutOcrResult:
    """Merge per-region OCR into column-major reading order.

    When *crop_origins* is set (one ``(x0, y0)`` per result), line boxes are
    crop-relative and positioned with the crop origin. Otherwise lines are
    positioned with ``region.left`` / ``region.top`` (legacy callers).
    """
    ordered: list[tuple[int, int, int, int, OcrLine]] = []
    for i, (region, result) in enumerate(results):
        if crop_origins is not None:
            ox, oy = crop_origins[i]
        else:
            ox, oy = region.left, region.top
        x_min = region.left
        x_max = region.left + region.width
        for line in result.lines:
            if not line.text.strip():
                continue
            abs_left = line.left + ox
            abs_top = line.top + oy
            line_right = abs_left + line.width
            if line_right <= x_min or abs_left >= x_max:
                continue
            ordered.append(
                (
                    region.sort_col,
                    region.sort_subcol,
                    region.sort_band,
                    abs_top,
                    OcrLine(
                        line_num=0,
                        text=line.text,
                        left=abs_left,
                        top=abs_top,
                        width=line.width,
                        height=line.height,
                        conf=line.conf,
                        section_id=region.section_id,
                    ),
                ),
            )

    # Column-major: page column, vertical band, sub-column x-order, then line top.
    ordered.sort(key=lambda item: (item[0], item[2], item[1], item[3]))
    lines = [replace(line, line_num=i) for i, (_, _, _, _, line) in enumerate(ordered, start=1)]
    full_text = "\n".join(l.text for l in lines if l.text.strip())
    return LayoutOcrResult(
        lines=lines,
        page_width=page_width,
        page_height=page_height,
        full_text=full_text,
        sections=sections,
    )


def ocr_image_regions(
    image: Path,
    regions: list[RegionBox],
    *,
    lang: str,
    psm: int,
    settings=None,
    filter_opts=None,
    log_label: str = "region-ocr",
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult | None:
    if len(regions) < 2:
        return None

    from PIL import Image

    from historical_ocr.lib.layout_ocr import ocr_pil_with_layout

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    with Image.open(image) as im:
        page_width, page_height = im.size
        rgb = im.convert("RGB")

    _log(f"{log_label}: {len(regions)} regions on {image.name}")

    region_results: list[tuple[RegionBox, LayoutOcrResult]] = []
    crop_origins: list[tuple[int, int]] = []
    for region in regions:
        pad = region.pad
        x0 = max(0, region.left - pad)
        y0 = max(0, region.top - pad)
        x1 = min(page_width, region.left + region.width + pad)
        y1 = min(page_height, region.top + region.height + pad)
        if x1 <= x0 or y1 <= y0:
            continue
        crop = rgb.crop((x0, y0, x1, y1))
        result = ocr_pil_with_layout(
            crop,
            lang=lang,
            psm=psm,
            settings=settings,
            filter_opts=filter_opts,
        )
        region_results.append((region, result))
        crop_origins.append((x0, y0))

    if not region_results:
        return None

    return merge_region_results(
        region_results,
        page_width=page_width,
        page_height=page_height,
        crop_origins=crop_origins,
    )
