"""Classify ink marks as letterforms, rules, symbols, or damage before keeping OCR tokens.

Uses lightweight connected-component metrics on Tesseract word crops (adapted from
manuscript-fingerprint's per-glyph shape pipeline) plus page-level letter-height
bands from line heatmaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

try:
    import numpy as np
except ImportError:  # pragma: no cover - print OCR installs numpy via pdf extra
    np = None  # type: ignore[assignment]


class MarkKind(str, Enum):
    LETTERFORM = "letterform"
    RULE = "rule"
    SYMBOL = "symbol"
    DAMAGE = "damage"
    STRANGE_LETTER = "strange_letter"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GlyphMetrics:
    width: int
    height: int
    aspect: float
    fill_ratio: float
    ink_pixels: int
    n_components: int
    median_component_h: float
    line_median_h: float


@dataclass(frozen=True)
class GlyphDecision:
    kind: MarkKind
    keep: bool
    reason: str
    metrics: GlyphMetrics | None = None


def _otsu_threshold(pixels) -> int:
    if np is None:
        return 128
    hist, _ = np.histogram(pixels.ravel(), bins=256, range=(0, 256))
    total = pixels.size
    if total == 0:
        return 128
    sum_total = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0.0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return int(threshold)


def _connected_components(binary) -> tuple[int, list[tuple[int, int, int, int, int]]]:
    """Return component count and (h, w, ink, y0, x0) per component."""
    if np is None:
        return 0, []
    try:
        from scipy.ndimage import find_objects, label
    except ImportError:
        return _connected_components_fallback(binary)

    labels, n = label(binary)
    if n == 0:
        return 0, []
    counts = np.bincount(labels.ravel(), minlength=n + 1)
    slices = find_objects(labels)
    out: list[tuple[int, int, int, int, int]] = []
    for i, sl in enumerate(slices):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        ink = int(counts[i + 1])
        out.append((h, w, ink, sl[0].start, sl[1].start))
    return n, out


def _connected_components_fallback(binary) -> tuple[int, list[tuple[int, int, int, int, int]]]:
    """Single-blob fallback when scipy is unavailable."""
    if np is None:
        return 0, []
    ys, xs = np.where(binary)
    if ys.size == 0:
        return 0, []
    h = int(ys.max() - ys.min() + 1)
    w = int(xs.max() - xs.min() + 1)
    return 1, [(h, w, int(ys.size), int(ys.min()), int(xs.min()))]


def measure_crop(crop_gray, *, line_median_h: float) -> GlyphMetrics | None:
    if np is None or crop_gray is None:
        return None
    arr = np.asarray(crop_gray, dtype=np.uint8)
    if arr.ndim != 2:
        arr = arr[..., 0]
    h, w = arr.shape
    if h < 2 or w < 2:
        return None

    thresh = _otsu_threshold(arr)
    if thresh <= 0:
        thresh = 127
    binary = arr < thresh
    ink_pixels = int(binary.sum())
    if ink_pixels == 0 and np is not None:
        binary = arr < int(np.percentile(arr, 35))
        ink_pixels = int(binary.sum())
    fill = ink_pixels / float(h * w)
    n_comp, comps = _connected_components(binary)
    comp_heights = [c[0] for c in comps if c[0] > 0]
    median_comp_h = float(np.median(comp_heights)) if comp_heights else float(h)

    return GlyphMetrics(
        width=w,
        height=h,
        aspect=w / max(h, 1),
        fill_ratio=fill,
        ink_pixels=ink_pixels,
        n_components=n_comp,
        median_component_h=median_comp_h,
        line_median_h=line_median_h,
    )


def classify_metrics(metrics: GlyphMetrics, *, text: str, conf: float) -> GlyphDecision:
    """Map glyph metrics + OCR token to a keep/drop decision."""
    token = text.strip()
    h = metrics.height
    w = metrics.width
    fill = metrics.fill_ratio
    aspect = metrics.aspect
    tall = h / max(w, 1)
    line_h = max(metrics.line_median_h, 1.0)

    if len(token) == 1:
        if token.isdigit():
            return GlyphDecision(MarkKind.DAMAGE, False, "lone_digit", metrics)
        if token in "@_":
            return GlyphDecision(MarkKind.SYMBOL, False, "lone_symbol", metrics)

    # Column / table rules — tall narrow strokes (solid or faint).
    if w <= max(4, line_h * 0.15) and h >= line_h * 1.2 and tall >= 2.5:
        return GlyphDecision(MarkKind.RULE, False, "vertical_rule", metrics)
    if aspect >= 3.0 and fill <= 0.40 and h <= line_h * 0.35:
        return GlyphDecision(MarkKind.RULE, False, "horizontal_rule", metrics)

    # Damage / noise — OCR should not invent letters here.
    if fill <= 0.04:
        return GlyphDecision(MarkKind.DAMAGE, False, "sparse_ink", metrics)
    if fill >= 0.55 and h <= line_h * 0.55 and w <= line_h * 0.55 and 0.6 <= aspect <= 1.6:
        if conf < 50 and not any(ch.isalnum() for ch in text):
            return GlyphDecision(MarkKind.DAMAGE, False, "ink_blob", metrics)
    if metrics.n_components >= 8 and fill <= 0.20:
        return GlyphDecision(MarkKind.DAMAGE, False, "fragmented_ink", metrics)

    # Letterforms — height band around the line's type body.
    rel_h = h / line_h
    if 0.35 <= rel_h <= 2.8 and 0.06 <= fill <= 0.82 and 0.12 <= aspect <= 2.8:
        if metrics.n_components <= 3 and (conf >= 45 or any(ch.isalnum() for ch in text)):
            return GlyphDecision(MarkKind.LETTERFORM, True, "letterform_band", metrics)

    # Intentional punctuation / symbols.
    if len(text.strip()) == 1 and conf >= 55 and fill >= 0.05:
        return GlyphDecision(MarkKind.SYMBOL, True, "symbol_high_conf", metrics)
    if len(text.strip()) == 1 and conf < 55:
        return GlyphDecision(MarkKind.SYMBOL, False, "symbol_low_conf", metrics)

    if conf >= 70:
        return GlyphDecision(MarkKind.LETTERFORM, True, "ocr_high_conf", metrics)

    return GlyphDecision(MarkKind.UNKNOWN, False, "ambiguous", metrics)


def classify_bbox(
    *,
    width: int,
    height: int,
    text: str,
    conf: float,
    line_median_h: float,
) -> GlyphDecision:
    """BBox-only fallback when crop analysis is unavailable."""
    line_h = max(line_median_h, 1.0)
    aspect = width / max(height, 1)
    tall = height / max(width, 1)
    rel_h = height / line_h

    if tall >= 3.5:
        return GlyphDecision(MarkKind.RULE, False, "bbox_vertical_rule", None)
    if aspect >= 3.5 and height <= line_h * 0.4:
        return GlyphDecision(MarkKind.RULE, False, "bbox_horizontal_rule", None)
    if rel_h >= 0.35 and rel_h <= 2.8 and conf >= 50:
        return GlyphDecision(MarkKind.LETTERFORM, True, "bbox_letter_band", None)
    if conf < 50 and not any(ch.isalnum() for ch in text):
        return GlyphDecision(MarkKind.SYMBOL, False, "bbox_low_conf_symbol", None)
    return GlyphDecision(MarkKind.UNKNOWN, conf >= 60, "bbox_fallback", None)


def _apply_font_check(
    decision: GlyphDecision,
    *,
    text: str,
    conf: float,
    font_profile=None,
) -> GlyphDecision:
    if font_profile is None:
        return decision
    from historical_ocr.lib.historical_fonts import analyze_token_for_font

    finding = analyze_token_for_font(text, font_profile, conf=conf)
    if finding is None or not finding.anomalous:
        return decision
    return GlyphDecision(
        MarkKind.STRANGE_LETTER,
        finding.keep,
        finding.reason,
        decision.metrics,
    )


def classify_token(
    *,
    text: str,
    conf: float,
    left: int,
    top: int,
    width: int,
    height: int,
    line_median_h: float,
    page_gray=None,
    font_profile=None,
) -> GlyphDecision:
    if page_gray is not None and np is not None and width > 0 and height > 0:
        arr = np.asarray(page_gray, dtype=np.uint8)
        H, W = arr.shape[:2]
        x0 = max(0, left)
        y0 = max(0, top)
        x1 = min(W, left + width)
        y1 = min(H, top + height)
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            crop = arr[y0:y1, x0:x1]
            metrics = measure_crop(crop, line_median_h=line_median_h)
            if metrics is not None:
                decision = classify_metrics(metrics, text=text, conf=conf)
                return _apply_font_check(
                    decision,
                    text=text,
                    conf=conf,
                    font_profile=font_profile,
                )

    decision = classify_bbox(
        width=width,
        height=height,
        text=text,
        conf=conf,
        line_median_h=line_median_h,
    )
    return _apply_font_check(decision, text=text, conf=conf, font_profile=font_profile)


def line_median_heights(data: dict) -> dict[tuple[int, int, int], float]:
    """Per Tesseract line key → median word height (letterform heatmap band)."""
    buckets: dict[tuple[int, int, int], list[int]] = {}
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text or not any(ch.isalnum() for ch in text):
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < 40:
            continue
        h = int(data["height"][i])
        if h < 4:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        buckets.setdefault(key, []).append(h)

    out: dict[tuple[int, int, int], float] = {}
    for key, heights in buckets.items():
        if not heights:
            continue
        if np is not None:
            out[key] = float(np.median(heights))
        else:
            sorted_h = sorted(heights)
            out[key] = float(sorted_h[len(sorted_h) // 2])
    return out


def page_median_letter_height(line_medians: dict[tuple[int, int, int], float]) -> float:
    if not line_medians:
        return 0.0
    vals = list(line_medians.values())
    if np is not None:
        return float(np.median(vals))
    vals.sort()
    return float(vals[len(vals) // 2])
