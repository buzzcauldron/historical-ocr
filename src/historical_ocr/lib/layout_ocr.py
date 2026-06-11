"""Print OCR with per-line layout from Tesseract."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class OcrLine:
    line_num: int
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    section_id: int | None = None


@dataclass(frozen=True)
class TeiSection:
    section_id: int
    section_type: str
    left: int
    top: int
    width: int
    height: int
    column_index: int = 0


@dataclass(frozen=True)
class LayoutOcrResult:
    lines: list[OcrLine]
    page_width: int
    page_height: int
    full_text: str
    sections: tuple[TeiSection, ...] = ()

    def to_json(self) -> str:
        payload: dict = {
            "page_width": self.page_width,
            "page_height": self.page_height,
            "full_text": self.full_text,
            "lines": [asdict(line) for line in self.lines],
        }
        if self.sections:
            payload["sections"] = [asdict(section) for section in self.sections]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> LayoutOcrResult:
        data = json.loads(raw)
        lines = [
            OcrLine(
                line_num=int(item["line_num"]),
                text=str(item["text"]),
                left=int(item["left"]),
                top=int(item["top"]),
                width=int(item["width"]),
                height=int(item["height"]),
                conf=float(item.get("conf", 0.0)),
                section_id=int(item["section_id"]) if item.get("section_id") is not None else None,
            )
            for item in data.get("lines", [])
        ]
        sections = tuple(
            TeiSection(
                section_id=int(item["section_id"]),
                section_type=str(item["section_type"]),
                left=int(item["left"]),
                top=int(item["top"]),
                width=int(item["width"]),
                height=int(item["height"]),
                column_index=int(item.get("column_index", 0)),
            )
            for item in data.get("sections", [])
        )
        return cls(
            lines=lines,
            page_width=int(data["page_width"]),
            page_height=int(data["page_height"]),
            full_text=str(data.get("full_text", "")),
            sections=sections,
        )


def _group_tesseract_lines(
    data: dict,
    *,
    filter_opts=None,
    page_gray=None,
    glyph_decisions_out: list | None = None,
) -> list[OcrLine]:
    from historical_ocr.lib.glyph_classify import (
        classify_token,
        line_median_heights,
        page_median_letter_height,
    )
    from historical_ocr.lib.symbol_filter import (
        SymbolFilterOptions,
        needs_glyph_review,
        should_drop_token,
    )

    opts = filter_opts or SymbolFilterOptions(enabled=False)
    line_heights = line_median_heights(data) if opts.glyph_filter else {}
    page_median_h = page_median_letter_height(line_heights)
    buckets: dict[tuple[int, int, int], list[tuple[str, int, int, int, int, float]]] = {}
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        line_h = line_heights.get(key) or page_median_h or float(height)

        glyph_decision = None
        if needs_glyph_review(text, conf, opts):
            glyph_decision = classify_token(
                text=text,
                conf=conf,
                left=left,
                top=top,
                width=width,
                height=height,
                line_median_h=line_h,
                page_gray=page_gray,
                font_profile=opts.font_profile,
            )
            if glyph_decisions_out is not None:
                glyph_decisions_out.append((left, top, width, height, glyph_decision))

        if should_drop_token(text, conf, opts, glyph_decision=glyph_decision):
            continue
        buckets.setdefault(key, []).append(
            (
                text,
                left,
                top,
                width,
                height,
                conf,
            ),
        )

    lines: list[OcrLine] = []
    for line_num, (_key, words) in enumerate(sorted(buckets.items()), start=1):
        words.sort(key=lambda w: w[1])
        text = " ".join(w[0] for w in words)
        left = min(w[1] for w in words)
        top = min(w[2] for w in words)
        right = max(w[1] + w[3] for w in words)
        bottom = max(w[2] + w[4] for w in words)
        conf = sum(w[5] for w in words) / len(words)
        lines.append(
            OcrLine(
                line_num=line_num,
                text=text,
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
                conf=conf,
            ),
        )
    return lines


def apply_symbol_filter_to_result(result: LayoutOcrResult, filter_opts) -> LayoutOcrResult:
    from historical_ocr.lib.symbol_filter import (
        SymbolFilterOptions,
        is_orphan_damage_line,
        sanitize_line,
        sanitize_ocr_text,
    )

    opts = filter_opts or SymbolFilterOptions(enabled=False)
    if not opts.enabled:
        return result

    if result.lines:
        updated: list[OcrLine] = []
        for line in result.lines:
            if is_orphan_damage_line(line.text, opts):
                continue
            clean = sanitize_line(line.text, opts)
            if not clean:
                continue
            updated.append(
                OcrLine(
                    line_num=line.line_num,
                    text=clean,
                    left=line.left,
                    top=line.top,
                    width=line.width,
                    height=line.height,
                    conf=line.conf,
                ),
            )
        full_text = "\n".join(l.text for l in updated)
        return LayoutOcrResult(
            lines=updated,
            page_width=result.page_width,
            page_height=result.page_height,
            full_text=full_text,
        )

    return LayoutOcrResult(
        lines=result.lines,
        page_width=result.page_width,
        page_height=result.page_height,
        full_text=sanitize_ocr_text(result.full_text, opts),
    )


def _tesseract_config(psm: int, filter_opts) -> str:
    from historical_ocr.backends import tesseract as tess_backend
    from historical_ocr.lib.symbol_filter import SymbolFilterOptions

    opts = filter_opts or SymbolFilterOptions(enabled=False)
    blacklist = opts.char_blacklist if opts.enabled else None
    whitelist = opts.char_whitelist if opts.enabled else None
    return tess_backend.build_config(
        psm=psm,
        char_blacklist=blacklist,
        char_whitelist=whitelist,
    )


def ocr_image_text_only(
    image: Path,
    *,
    lang: str = "lat+frk+eng",
    psm: int = 6,
    settings=None,
    filter_opts=None,
) -> LayoutOcrResult:
    """Fast Tesseract pass: ``image_to_string`` only (no per-word layout scan)."""
    from historical_ocr.backends import tesseract as tess_backend
    import pytesseract

    if settings is not None:
        tess_backend.configure_from_settings(settings)
        lang = tess_backend.resolve_lang_bundle(lang, settings)
    tess_backend.ensure_ready(lang, settings=settings)

    config = _tesseract_config(psm, filter_opts)
    with Image.open(image) as im:
        page_width, page_height = im.size
        text = pytesseract.image_to_string(im, lang=lang, config=config)
    result = LayoutOcrResult(
        lines=[],
        page_width=page_width,
        page_height=page_height,
        full_text=text.strip(),
    )
    return apply_symbol_filter_to_result(result, filter_opts)


def ocr_pil_with_layout(
    im: Image.Image,
    *,
    lang: str = "lat+frk+eng",
    psm: int = 6,
    settings=None,
    filter_opts=None,
    x_offset: int = 0,
    y_offset: int = 0,
    persist_glyph_for: Path | None = None,
) -> LayoutOcrResult:
    from historical_ocr.backends import tesseract as tess_backend
    from pytesseract import Output

    if settings is not None:
        tess_backend.configure_from_settings(settings)
        lang = tess_backend.resolve_lang_bundle(lang, settings)
    tess_backend.ensure_ready(lang, settings=settings)

    import pytesseract

    config = _tesseract_config(psm, filter_opts)
    glyph_decisions: list = []
    page_width, page_height = im.size
    page_gray = im.convert("L") if filter_opts and filter_opts.glyph_filter else None
    data = pytesseract.image_to_data(
        im,
        lang=lang,
        config=config,
        output_type=Output.DICT,
    )

    gray_arr = None
    if page_gray is not None:
        try:
            import numpy as np

            gray_arr = np.asarray(page_gray, dtype=np.uint8)
        except ImportError:
            gray_arr = None

    lines = _group_tesseract_lines(
        data,
        filter_opts=filter_opts,
        page_gray=gray_arr,
        glyph_decisions_out=glyph_decisions if filter_opts and filter_opts.glyph_filter else None,
    )

    if x_offset or y_offset:
        shifted: list[OcrLine] = []
        for line in lines:
            shifted.append(
                OcrLine(
                    line_num=line.line_num,
                    text=line.text,
                    left=line.left + x_offset,
                    top=line.top + y_offset,
                    width=line.width,
                    height=line.height,
                    conf=line.conf,
                ),
            )
        lines = shifted

    if filter_opts and filter_opts.glyph_filter and glyph_decisions and persist_glyph_for is not None:
        from historical_ocr.lib.glyph_heatmap import persist_glyph_decisions

        job_root = (
            persist_glyph_for.parent.parent
            if persist_glyph_for.parent.name == "pages"
            else persist_glyph_for.parent
        )
        persist_glyph_decisions(job_root, persist_glyph_for.stem, glyph_decisions)

    full_text = "\n".join(line.text for line in lines if line.text.strip())
    result = LayoutOcrResult(
        lines=lines,
        page_width=page_width,
        page_height=page_height,
        full_text=full_text,
    )
    return apply_symbol_filter_to_result(result, filter_opts)


def ocr_image_with_layout(
    image: Path,
    *,
    lang: str = "lat+frk+eng",
    psm: int = 6,
    settings=None,
    filter_opts=None,
) -> LayoutOcrResult:
    with Image.open(image) as im:
        return ocr_pil_with_layout(
            im,
            lang=lang,
            psm=psm,
            settings=settings,
            filter_opts=filter_opts,
            persist_glyph_for=image,
        )


def write_layout_json(result: LayoutOcrResult, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(result.to_json() + "\n", encoding="utf-8")


def read_layout_json(path: Path) -> LayoutOcrResult | None:
    if not path.is_file():
        return None
    return LayoutOcrResult.from_json(path.read_text(encoding="utf-8"))
