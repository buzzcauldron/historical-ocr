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


_INK_THRESHOLD = 175
_BODY_MAX_INK_SPAN_FRAC = 0.55


def _smooth_1d(data, kernel: int):
    if np is None:
        return data
    if kernel % 2 == 0:
        kernel += 1
    pad = kernel // 2
    padded = np.pad(data, (pad, pad), mode="edge")
    return np.convolve(padded, np.ones(kernel) / kernel, mode="valid")


def _longest_ink_run(row) -> int:
    best = 0
    run = 0
    for pixel in row:
        if pixel:
            run += 1
            if run > best:
                best = run
        else:
            run = 0
    return best


def _body_row_mask(ink, *, max_ink_span_frac: float = _BODY_MAX_INK_SPAN_FRAC):
    """Exclude rows whose longest continuous ink span crosses most of the page width."""
    h, w = ink.shape
    if w <= 0:
        return np.zeros(h, dtype=bool) if np is not None else []

    body = np.zeros(h, dtype=bool)
    threshold = w * max_ink_span_frac
    for y in range(h):
        if not ink[y].any():
            continue
        if _longest_ink_run(ink[y]) < threshold:
            body[y] = True
    return body


def vertical_ink_projection(
    gray,
    *,
    max_ink_span_frac: float = _BODY_MAX_INK_SPAN_FRAC,
    ink_threshold: int = _INK_THRESHOLD,
):
    """1D ink-density profile from body text rows (heatmap column-sum)."""
    if np is None:
        return None

    arr = np.asarray(gray, dtype=np.uint8)
    if arr.ndim != 2:
        return None

    ink = arr < ink_threshold
    body = _body_row_mask(ink, max_ink_span_frac=max_ink_span_frac)
    proj = (ink & body[:, None]).sum(axis=0).astype(np.float64)
    w = arr.shape[1]
    kernel = max(9, w // 100)
    return _smooth_1d(proj, kernel)


def _active_ink_zone_columns(
    sm,
    w: int,
    *,
    min_column_frac: float,
) -> list[tuple[int, int]]:
    """Columns as separated high-ink plateaus in the vertical heatmap."""
    min_w = int(w * min_column_frac)
    for thresh_frac in (0.32, 0.26, 0.20, 0.15):
        threshold = float(sm.max()) * thresh_frac
        active = sm > threshold
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for x in range(w):
            if active[x]:
                if start is None:
                    start = x
            elif start is not None:
                if x - start >= min_w:
                    runs.append((start, x))
                start = None
        if start is not None and w - start >= min_w:
            runs.append((start, w))
        if len(runs) >= 2:
            return runs
    return []


def _split_widest_into_n(
    sm,
    w: int,
    n: int,
    *,
    min_column_frac: float,
) -> list[tuple[int, int]]:
    """Recursively split the widest column at the deepest ink gutter."""
    min_w = int(w * min_column_frac)
    bounds = [(0, w)]
    while len(bounds) < n:
        widest_i = max(range(len(bounds)), key=lambda i: bounds[i][1] - bounds[i][0])
        x0, x1 = bounds[widest_i]
        if x1 - x0 < 2 * min_w:
            break
        interior = range(x0 + min_w, x1 - min_w + 1)
        if not interior:
            break
        split = min(interior, key=lambda x: sm[x])
        bounds = bounds[:widest_i] + [(x0, split), (split, x1)] + bounds[widest_i + 1 :]
    return bounds if len(bounds) >= 2 else []


def _photo_heavy_fraction(gray) -> float:
    """Share of rows with a wide ink span (illustrations, mastheads)."""
    if np is None:
        return 0.0

    arr = np.asarray(gray, dtype=np.uint8)
    if arr.ndim != 2:
        return 0.0

    ink = arr < _INK_THRESHOLD
    h, w = ink.shape
    if h <= 0 or w <= 0:
        return 0.0

    wide_rows = sum(
        1 for y in range(h) if ink[y].any() and _longest_ink_run(ink[y]) >= w * 0.45
    )
    return wide_rows / h


_MIN_INTERIOR_INK_FRAC = 0.12
_MIN_FIRST_COL_INK_FRAC = 0.18
_MIN_EDGE_INK_FRAC = 0.05
_MIN_SUBSTANTIVE_INK_FRAC = 0.14


def _column_ink_masses_ok(bounds: list[tuple[int, int]], sm) -> bool:
    """Reject splits that carve out low-ink slivers between real columns."""
    masses = [float(sm[x0:x1].sum()) for x0, x1 in bounds]
    total = sum(masses)
    if total <= 0:
        return False

    rel = [mass / total for mass in masses]
    n = len(bounds)

    for j in range(1, n - 1):
        if rel[j] < _MIN_INTERIOR_INK_FRAC:
            return False

    if n >= 4 and rel[0] < _MIN_FIRST_COL_INK_FRAC:
        return False

    for j in (0, n - 1):
        if rel[j] < _MIN_EDGE_INK_FRAC:
            return False

    substantive = sum(1 for fraction in rel if fraction >= _MIN_SUBSTANTIVE_INK_FRAC)
    if n >= 3 and substantive < n:
        edge_thin = rel[0] < _MIN_SUBSTANTIVE_INK_FRAC or rel[-1] < _MIN_SUBSTANTIVE_INK_FRAC
        if not (edge_thin and substantive >= n - 1):
            return False

    return True


def _column_widths_ok(widths: list[int]) -> bool:
    """Allow a thin margin strip; require core columns to be reasonably even."""
    n = len(widths)
    if n < 2:
        return False

    mean = sum(widths) / n
    if mean <= 0:
        return False

    if n == 2:
        return min(widths) / max(widths) >= 0.08

    core = [w for w in widths if w >= mean * 0.32]
    if len(core) < 2:
        return False

    core_mean = sum(core) / len(core)
    return min(core) / core_mean >= 0.35


def _score_column_layout(
    bounds: list[tuple[int, int]],
    sm,
    *,
    photo_frac: float = 0.0,
) -> float:
    widths = [x1 - x0 for x0, x1 in bounds]
    n = len(widths)
    if n < 2 or not _column_widths_ok(widths) or not _column_ink_masses_ok(bounds, sm):
        return -1e9

    mean = sum(widths) / n
    cv = (sum((width - mean) ** 2 for width in widths) / n) ** 0.5 / mean
    gutter = sum(float(sm.max()) - float(sm[x1]) for _, x1 in bounds[:-1])
    uniformity = max(0.0, 1.0 - cv / 0.35)
    bonus = {2: 250, 3: 400, 4: 550, 5: 200}.get(n, -200) * uniformity
    over_cols_penalty = -2400 * max(0, n - 4)
    if photo_frac >= 0.12 and n > 3:
        over_cols_penalty -= 500 * (n - 3)
    return gutter - cv * 400 + bonus + over_cols_penalty


def _pick_best_column_layout(
    candidates: list[list[tuple[int, int]]],
    sm,
    *,
    photo_frac: float = 0.0,
) -> list[tuple[int, int]]:
    scored: list[tuple[float, list[tuple[int, int]]]] = []
    for bounds in candidates:
        if len(bounds) < 2:
            continue
        score = _score_column_layout(bounds, sm, photo_frac=photo_frac)
        if score > -1e8:
            scored.append((score, bounds))
    if not scored:
        return []

    best_score, best_bounds = max(scored, key=lambda item: item[0])
    close_eps = 250.0
    for score, bounds in sorted(scored, key=lambda item: (-item[0], len(item[1]))):
        if (
            len(bounds) < len(best_bounds)
            and best_score - score <= close_eps
        ):
            return bounds
    return best_bounds


def detect_column_bounds(
    gray,
    *,
    min_gutter_px: int = 14,
    min_column_frac: float = 0.12,
    max_ink_span_frac: float = _BODY_MAX_INK_SPAN_FRAC,
) -> list[tuple[int, int]]:
    """Return ``(x0, x1)`` column ranges from the ink-zone vertical heatmap."""
    if np is None:
        w = gray.shape[1] if hasattr(gray, "shape") else 0
        return [(0, w)]

    arr = np.asarray(gray, dtype=np.uint8)
    if arr.ndim != 2:
        return [(0, arr.shape[1])]

    w = arr.shape[1]
    sm = vertical_ink_projection(arr, max_ink_span_frac=max_ink_span_frac)
    if sm is None or sm.max() <= 0:
        return [(0, w)]

    candidates: list[list[tuple[int, int]]] = []

    zones = _active_ink_zone_columns(sm, w, min_column_frac=min_column_frac)
    if len(zones) >= 2:
        candidates.append(zones)

    for n in range(2, 6):
        split = _split_widest_into_n(
            sm,
            w,
            n,
            min_column_frac=max(min_column_frac, 0.10),
        )
        if len(split) >= 2:
            candidates.append(split)

    photo_frac = _photo_heavy_fraction(arr)
    columns = _pick_best_column_layout(candidates, sm, photo_frac=photo_frac)
    return columns if len(columns) >= 2 else [(0, w)]


def column_bounds_from_layout(layout: InkLayout) -> list[tuple[int, int]]:
    return [(col.left, col.left + col.width) for col in layout.columns]


def has_multiple_columns(gray, **kwargs) -> bool:
    return len(detect_column_bounds(gray, **kwargs)) >= 2


def column_count_from_ink_zones(gray, **kwargs) -> int:
    return len(detect_column_bounds(gray, **kwargs))


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

    if not layout.columns and not layout.sections:
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
