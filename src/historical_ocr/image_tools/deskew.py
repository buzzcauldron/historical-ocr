"""Page deskew — uses typebox-fingerprinter when installed, else projection fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class DeskewMeta:
    angle_degrees: float
    applied: bool
    method: str


def _import_deskew():
    try:
        from manuscript_fingerprint.deskew import deskew_pil as _deskew_pil
        from manuscript_fingerprint.deskew import estimate_skew_angle as _estimate

        return _deskew_pil, _estimate
    except ImportError:
        from historical_ocr.image_tools._deskew_fallback import deskew_pil as _deskew_pil
        from historical_ocr.image_tools._deskew_fallback import estimate_skew_angle as _estimate

        return _deskew_pil, _estimate


def deskew_image(
    image: Image.Image,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> tuple[Image.Image, DeskewMeta]:
    deskew_pil, _ = _import_deskew()
    out, result = deskew_pil(
        image,
        max_angle=max_angle,
        min_abs_angle=min_abs_angle,
    )
    return out, DeskewMeta(
        angle_degrees=result.angle_degrees,
        applied=result.applied,
        method=result.method,
    )


def deskew_path(
    src: Path,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> tuple[Image.Image, DeskewMeta]:
    with Image.open(src) as im:
        return deskew_image(im.convert("RGB"), max_angle=max_angle, min_abs_angle=min_abs_angle)
