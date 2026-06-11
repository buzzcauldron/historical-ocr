"""Numpy/PIL deskew fallback when typebox-fingerprinter is not installed."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class DeskewResult:
    angle_degrees: float
    applied: bool
    method: str = "projection"


def estimate_skew_angle(
    image: Image.Image,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> tuple[float, str]:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    im = Image.fromarray(gray, mode="L")
    best_angle = 0.0
    best_score = -1.0
    step = 0.5
    cap = min(max_angle, 12.0)
    for a in np.arange(-cap, cap + step * 0.5, step):
        rotated = im.rotate(-float(a), resample=Image.Resampling.BILINEAR, expand=False, fillcolor=255)
        arr = np.asarray(rotated, dtype=np.float32)
        ink = (255.0 - arr) > 30
        if ink.sum() < 200:
            continue
        score = float(ink.sum(axis=1).var())
        if score > best_score:
            best_score = score
            best_angle = float(a)
    if abs(best_angle) < min_abs_angle:
        return 0.0, "projection"
    return best_angle, "projection"


def deskew_pil(
    image: Image.Image,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
    background: int | tuple[int, ...] = 255,
) -> tuple[Image.Image, DeskewResult]:
    angle, method = estimate_skew_angle(
        image,
        max_angle=max_angle,
        min_abs_angle=min_abs_angle,
    )
    if abs(angle) < min_abs_angle:
        return image, DeskewResult(angle_degrees=0.0, applied=False, method=method)
    rgb = image.convert("RGB") if image.mode != "RGB" else image
    fill = background if isinstance(background, tuple) else (background, background, background)
    out = rgb.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)
    return out, DeskewResult(angle_degrees=angle, applied=True, method=method)
