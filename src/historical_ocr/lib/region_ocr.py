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
    sort_band: int = 0
    section_id: int | None = None
    pad: int = 4


def merge_region_results(
    results: list[tuple[RegionBox, LayoutOcrResult]],
    *,
    page_width: int,
    page_height: int,
    sections: tuple = (),
) -> LayoutOcrResult:
    ordered: list[tuple[int, int, int, OcrLine]] = []
    for region, result in results:
        for line in result.lines:
            if not line.text.strip():
                continue
            ordered.append(
                (
                    region.sort_col,
                    region.sort_band,
                    line.top,
                    OcrLine(
                        line_num=0,
                        text=line.text,
                        left=line.left + region.left,
                        top=line.top + region.top,
                        width=line.width,
                        height=line.height,
                        conf=line.conf,
                        section_id=region.section_id,
                    ),
                ),
            )

    ordered.sort(key=lambda item: (item[0], item[1], item[2]))
    lines = [replace(line, line_num=i) for i, (_, _, _, line) in enumerate(ordered, start=1)]
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
            x_offset=x0,
            y_offset=y0,
        )
        region_results.append((region, result))

    if not region_results:
        return None

    return merge_region_results(
        region_results,
        page_width=page_width,
        page_height=page_height,
    )
