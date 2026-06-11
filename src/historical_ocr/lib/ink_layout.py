"""Ink projection layout — columns and text bands before OCR."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]


@dataclass(frozen=True)
class InkColumn:
    index: int
    left: int
    width: int


@dataclass(frozen=True)
class InkSection:
    section_id: int
    left: int
    top: int
    width: int
    height: int
    column_index: int = 0


@dataclass(frozen=True)
class InkLayout:
    page_width: int
    page_height: int
    columns: tuple[InkColumn, ...]
    sections: tuple[InkSection, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "page_width": self.page_width,
                "page_height": self.page_height,
                "columns": [asdict(col) for col in self.columns],
                "sections": [asdict(sec) for sec in self.sections],
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> InkLayout:
        data = json.loads(raw)
        columns = tuple(
            InkColumn(
                index=int(item["index"]),
                left=int(item["left"]),
                width=int(item["width"]),
            )
            for item in data.get("columns", [])
        )
        sections = tuple(
            InkSection(
                section_id=int(item["section_id"]),
                left=int(item["left"]),
                top=int(item["top"]),
                width=int(item["width"]),
                height=int(item["height"]),
                column_index=int(item.get("column_index", 0)),
            )
            for item in data.get("sections", [])
        )
        return cls(
            page_width=int(data["page_width"]),
            page_height=int(data["page_height"]),
            columns=columns,
            sections=sections,
        )


def detect_column_bounds(
    gray,
    *,
    min_gutter_px: int = 14,
    min_column_frac: float = 0.12,
) -> list[tuple[int, int]]:
    """Return ``(x0, x1)`` pixel ranges for text columns from a vertical ink projection."""
    if np is None:
        w = gray.shape[1] if hasattr(gray, "shape") else 0
        return [(0, w)]

    arr = np.asarray(gray, dtype=np.uint8)
    if arr.ndim != 2:
        return [(0, arr.shape[1])]

    h, w = arr.shape
    sample = arr[: max(1, int(h * 0.92)), :]
    ink = sample < 175
    proj = ink.sum(axis=0).astype(np.float64)
    if proj.max() <= 0:
        return [(0, w)]

    kernel = max(5, w // 200)
    if kernel % 2 == 0:
        kernel += 1
    pad = kernel // 2
    padded = np.pad(proj, (pad, pad), mode="edge")
    smoothed = np.convolve(padded, np.ones(kernel) / kernel, mode="valid")

    threshold = float(smoothed.max()) * 0.08
    gutters: list[int] = []
    in_gutter = False
    gutter_start = 0
    for x in range(w):
        if smoothed[x] <= threshold:
            if not in_gutter:
                gutter_start = x
                in_gutter = True
        elif in_gutter:
            if x - gutter_start >= min_gutter_px:
                gutters.append((gutter_start + x) // 2)
            in_gutter = False

    if not gutters:
        return [(0, w)]

    splits = [0, *gutters, w]
    min_w = int(w * min_column_frac)
    columns: list[tuple[int, int]] = []
    for i in range(len(splits) - 1):
        x0, x1 = splits[i], splits[i + 1]
        if x1 - x0 >= min_w:
            columns.append((x0, x1))

    return columns if len(columns) >= 2 else [(0, w)]


def detect_horizontal_bands(
    gray,
    x0: int,
    x1: int,
    *,
    min_gap_px: int = 18,
    min_band_px: int = 35,
) -> list[tuple[int, int]]:
    """Return ``(y0, y1)`` bands of ink within a column strip."""
    if np is None:
        return []

    arr = np.asarray(gray, dtype=np.uint8)
    col = arr[:, x0:x1]
    ink = col < 175
    proj = ink.sum(axis=1).astype(np.float64)
    if proj.max() <= 0:
        return []

    kernel = max(3, arr.shape[0] // 400)
    if kernel % 2 == 0:
        kernel += 1
    pad = kernel // 2
    padded = np.pad(proj, (pad, pad), mode="edge")
    smoothed = np.convolve(padded, np.ones(kernel) / kernel, mode="valid")

    threshold = float(smoothed.max()) * 0.06
    bands: list[tuple[int, int]] = []
    in_band = False
    band_start = 0
    gap_start = 0
    in_gap = False

    for y in range(arr.shape[0]):
        if smoothed[y] > threshold:
            if in_gap:
                if y - gap_start >= min_gap_px and in_band:
                    if y - band_start >= min_band_px:
                        bands.append((band_start, gap_start))
                    in_band = False
                in_gap = False
            if not in_band:
                band_start = y
                in_band = True
        else:
            if in_band and not in_gap:
                gap_start = y
                in_gap = True

    if in_band and arr.shape[0] - band_start >= min_band_px:
        bands.append((band_start, arr.shape[0]))

    return bands


def analyze_ink_layout(
    gray,
    *,
    page_width: int,
    page_height: int,
    min_gutter_px: int = 14,
    min_gap_px: int = 18,
    min_band_px: int = 35,
) -> InkLayout:
    """Detect column gutters and horizontal ink bands (pre-OCR page structure)."""
    column_bounds = detect_column_bounds(gray, min_gutter_px=min_gutter_px)
    columns: list[InkColumn] = []
    sections: list[InkSection] = []
    section_id = 1

    for col_idx, (x0, x1) in enumerate(column_bounds):
        columns.append(InkColumn(index=col_idx, left=x0, width=x1 - x0))
        bands = detect_horizontal_bands(
            gray,
            x0,
            x1,
            min_gap_px=min_gap_px,
            min_band_px=min_band_px,
        )
        if not bands:
            sections.append(
                InkSection(
                    section_id=section_id,
                    left=x0,
                    top=0,
                    width=x1 - x0,
                    height=page_height,
                    column_index=col_idx,
                ),
            )
            section_id += 1
            continue

        for y0, y1 in bands:
            sections.append(
                InkSection(
                    section_id=section_id,
                    left=x0,
                    top=y0,
                    width=x1 - x0,
                    height=y1 - y0,
                    column_index=col_idx,
                ),
            )
            section_id += 1

    return InkLayout(
        page_width=page_width,
        page_height=page_height,
        columns=tuple(columns),
        sections=tuple(sections),
    )


def analyze_ink_layout_image(
    image: Path,
    *,
    min_gutter_px: int = 14,
    min_gap_px: int = 18,
    min_band_px: int = 35,
) -> InkLayout | None:
    from PIL import Image

    image = image.expanduser().resolve()
    if not image.is_file():
        return None
    with Image.open(image) as im:
        page_width, page_height = im.size
        gray = im.convert("L")
    return analyze_ink_layout(
        gray,
        page_width=page_width,
        page_height=page_height,
        min_gutter_px=min_gutter_px,
        min_gap_px=min_gap_px,
        min_band_px=min_band_px,
    )


def ink_layout_path(job_root: Path, page_id: str) -> Path:
    return job_root / "artifacts" / page_id / "ink_layout.json"


def persist_ink_layout(job_root: Path, page_id: str, layout: InkLayout) -> Path:
    path = ink_layout_path(job_root, page_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(layout.to_json() + "\n", encoding="utf-8")
    return path


def read_ink_layout(path: Path) -> InkLayout | None:
    if not path.is_file():
        return None
    try:
        return InkLayout.from_json(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


_COLUMN_RGBA = (0, 188, 212, 90)
_SECTION_RGBA = (
    (63, 81, 181, 55),
    (103, 58, 183, 55),
    (0, 150, 136, 55),
)


def draw_ink_layout_overlay(draw, layout: InkLayout, *, scale: float = 1.0) -> None:
    """Draw column outlines and section fills on a PIL ImageDraw overlay."""

    def _box(left: int, top: int, width: int, height: int) -> tuple[int, int, int, int]:
        x0 = int(left * scale)
        y0 = int(top * scale)
        x1 = x0 + max(1, int(width * scale))
        y1 = y0 + max(1, int(height * scale))
        return x0, y0, x1, y1

    for col in layout.columns:
        x0, y0, x1, y1 = _box(col.left, 0, col.width, layout.page_height)
        draw.rectangle((x0, y0, x1, y1), outline=_COLUMN_RGBA[:3] + (170,), width=1)

    for section in layout.sections:
        rgba = _SECTION_RGBA[section.column_index % len(_SECTION_RGBA)]
        x0, y0, x1, y1 = _box(section.left, section.top, section.width, section.height)
        draw.rectangle((x0, y0, x1, y1), fill=rgba, outline=rgba[:3] + (120,))


def render_ink_layout_heatmap(
    image_path: Path,
    output_path: Path,
    layout: InkLayout,
    *,
    max_width: int = 1400,
) -> bool:
    """Overlay detected columns (cyan) and ink bands (indigo/teal) on the page scan."""
    from PIL import Image, ImageDraw

    if not layout.sections:
        return False

    image_path = Path(image_path)
    output_path = Path(output_path)
    with Image.open(image_path) as im:
        base = im.convert("RGB")

    w, h = base.size
    scale = 1.0
    if w > max_width:
        scale = max_width / w
        base = base.resize((max_width, max(1, int(h * scale))), Image.BILINEAR)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_ink_layout_overlay(draw, layout, scale=scale)

    out = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, format="PNG", optimize=True)
    return True
