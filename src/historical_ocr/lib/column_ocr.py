"""Multi-column newspaper OCR via shared region OCR."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from historical_ocr.lib.ink_layout import detect_column_bounds
from historical_ocr.lib.layout_ocr import LayoutOcrResult
from historical_ocr.lib.region_ocr import RegionBox, ocr_image_regions

__all__ = ["detect_column_bounds", "ocr_image_by_columns"]


def ocr_image_by_columns(
    image: Path,
    *,
    lang: str,
    psm: int,
    settings=None,
    filter_opts=None,
    min_gutter_px: int = 14,
    column_pad_px: int = 6,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult | None:
    from PIL import Image

    with Image.open(image) as im:
        page_h = im.size[1]
        bounds = detect_column_bounds(im.convert("L"), min_gutter_px=min_gutter_px)

    if len(bounds) < 2:
        return None

    regions = [
        RegionBox(
            left=x0,
            top=0,
            width=x1 - x0,
            height=page_h,
            sort_col=idx,
            pad=column_pad_px,
        )
        for idx, (x0, x1) in enumerate(bounds)
    ]

    return ocr_image_regions(
        image,
        regions,
        lang=lang,
        psm=psm,
        settings=settings,
        filter_opts=filter_opts,
        log_label="column-ocr",
        log_fn=log_fn,
    )
