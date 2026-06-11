"""TEI-oriented page sectioning for multi-region newspaper OCR."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

from historical_ocr.lib.ink_layout import analyze_ink_layout
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, TeiSection
from historical_ocr.lib.region_ocr import RegionBox, ocr_image_regions

_LIST_LINE_RE = re.compile(r"^\s*\d+\.")
_AD_HINT_RE = re.compile(
    r"\b(SHOP|CO\.|INC\.|AVE\.|ST\.|SPRINGFIELD|BARGAIN|FURNITURE|Nobby|FAIR)\b",
    re.I,
)
_ALL_CAPS_RE = re.compile(r"^[A-Z0-9\s\.\-\&\'\"]{6,}$")


def ink_sections_to_tei(ink) -> list[TeiSection]:
    return [
        TeiSection(
            section_id=sec.section_id,
            section_type="section",
            left=sec.left,
            top=sec.top,
            width=sec.width,
            height=sec.height,
            column_index=sec.column_index,
        )
        for sec in ink.sections
    ]


def detect_page_sections(
    gray,
    *,
    min_gutter_px: int = 14,
    min_gap_px: int = 18,
    min_band_px: int = 35,
) -> list[TeiSection]:
    h = int(gray.shape[0]) if hasattr(gray, "shape") else 0
    w = int(gray.shape[1]) if hasattr(gray, "shape") else 0
    ink = analyze_ink_layout(
        gray,
        page_width=w,
        page_height=h,
        min_gutter_px=min_gutter_px,
        min_gap_px=min_gap_px,
        min_band_px=min_band_px,
    )
    return ink_sections_to_tei(ink)


def classify_section(
    lines: list[OcrLine],
    section: TeiSection,
    *,
    page_height: int,
) -> str:
    texts = [ln.text.strip() for ln in lines if ln.text.strip()]
    if not texts:
        if section.top < page_height * 0.08:
            return "header"
        return "other"

    if section.top < page_height * 0.07 and len(texts) <= 4:
        return "header"

    list_hits = sum(1 for t in texts if _LIST_LINE_RE.match(t))
    if list_hits >= max(2, len(texts) // 2):
        return "list"

    joined = " ".join(texts)
    if len(texts) <= 14 and (_AD_HINT_RE.search(joined) or sum(1 for t in texts if _ALL_CAPS_RE.match(t)) >= 2):
        return "advertisement"

    return "article"


def refine_section_types(
    sections: list[TeiSection],
    lines: list[OcrLine],
    *,
    page_height: int,
) -> list[TeiSection]:
    by_section: dict[int, list[OcrLine]] = {}
    for line in lines:
        if line.section_id is None:
            continue
        by_section.setdefault(line.section_id, []).append(line)

    refined: list[TeiSection] = []
    for section in sections:
        sect_lines = by_section.get(section.section_id, [])
        section_type = classify_section(sect_lines, section, page_height=page_height)
        refined.append(replace(section, section_type=section_type))
    return refined


def ocr_image_by_tei_sections(
    image: Path,
    *,
    lang: str,
    psm: int,
    settings=None,
    filter_opts=None,
    min_gutter_px: int = 14,
    min_gap_px: int = 18,
    section_pad_px: int = 4,
    log_fn: Callable[[str], None] | None = None,
) -> LayoutOcrResult | None:
    from PIL import Image

    with Image.open(image) as im:
        page_width, page_height = im.size
        sections = detect_page_sections(
            im.convert("L"),
            min_gutter_px=min_gutter_px,
            min_gap_px=min_gap_px,
        )

    if len(sections) < 2:
        return None

    regions = [
        RegionBox(
            left=section.left,
            top=section.top,
            width=section.width,
            height=section.height,
            sort_col=section.column_index,
            sort_band=section.top,
            section_id=section.section_id,
            pad=section_pad_px,
        )
        for section in sections
    ]

    base = ocr_image_regions(
        image,
        regions,
        lang=lang,
        psm=psm,
        settings=settings,
        filter_opts=filter_opts,
        log_label="tei-section-ocr",
        log_fn=log_fn,
    )
    if base is None:
        return None

    refined = refine_section_types(list(sections), base.lines, page_height=page_height)
    return LayoutOcrResult(
        lines=base.lines,
        page_width=page_width,
        page_height=page_height,
        full_text=base.full_text,
        sections=tuple(refined),
    )
