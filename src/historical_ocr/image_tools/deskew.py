"""Page deskew — projection-variance method, no external dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class DeskewMeta:
    angle_degrees: float
    applied: bool
    method: str = "projection"


def estimate_skew_angle(
    image: Image.Image,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
    probe_size: int = 900,
) -> tuple[float, str]:
    """Return (angle_degrees, method). Angle is 0.0 if below threshold.

    Downscales to probe_size before the rotation loop so large scans
    don't cause hangs on low-spec hardware.
    """
    gray = image.convert("L")
    # Downscale for the angle-search loop — accuracy is not affected
    w, h = gray.size
    scale = min(1.0, probe_size / max(w, h))
    if scale < 1.0:
        gray = gray.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    arr_gray = np.asarray(gray, dtype=np.uint8)
    im = Image.fromarray(arr_gray, mode="L")
    best_angle = 0.0
    best_score = -1.0
    step = 0.5
    cap = min(max_angle, 12.0)
    for a in np.arange(-cap, cap + step * 0.5, step):
        rotated = im.rotate(
            -float(a),
            resample=Image.Resampling.BILINEAR,
            expand=False,
            fillcolor=255,
        )
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
) -> tuple[Image.Image, DeskewMeta]:
    """Rotate image to correct estimated skew. Returns (image, metadata)."""
    angle, method = estimate_skew_angle(
        image,
        max_angle=max_angle,
        min_abs_angle=min_abs_angle,
    )
    if abs(angle) < min_abs_angle:
        return image, DeskewMeta(angle_degrees=0.0, applied=False, method=method)
    rgb = image.convert("RGB") if image.mode not in ("RGB", "RGBA", "LA") else image
    fill = background if isinstance(background, tuple) else (background, background, background)
    out = rgb.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)
    return out, DeskewMeta(angle_degrees=angle, applied=True, method=method)


def deskew_image(
    image: Image.Image,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> tuple[Image.Image, DeskewMeta]:
    return deskew_pil(image, max_angle=max_angle, min_abs_angle=min_abs_angle)


def deskew_path(
    src: Path,
    *,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> tuple[Image.Image, DeskewMeta]:
    with Image.open(src) as im:
        return deskew_image(im.convert("RGB"), max_angle=max_angle, min_abs_angle=min_abs_angle)


def deskew_file(
    src: Path,
    dst: Path | None = None,
    *,
    in_place: bool = False,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> DeskewMeta:
    src = src.expanduser().resolve()
    if in_place:
        dst = src
    elif dst is None:
        dst = src.with_name(f"{src.stem}_deskewed{src.suffix}")
    else:
        dst = dst.expanduser().resolve()

    with Image.open(src) as im:
        out, meta = deskew_pil(im, max_angle=max_angle, min_abs_angle=min_abs_angle)
        dst.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs: dict = {}
        if dst.suffix.lower() in (".jpg", ".jpeg"):
            save_kwargs = {"quality": 92, "optimize": True}
        out.save(dst, **save_kwargs)
    return meta


def deskew_job_pages(
    job_dir: Path,
    *,
    pages_subdir: str = "01_pages",
    in_place: bool = True,
    max_angle: float = 15.0,
    min_abs_angle: float = 0.25,
) -> list[tuple[Path, DeskewMeta]]:
    """Deskew all page images under ``job_dir/01_pages`` (fingerprint scan layout)."""
    pages_dir = Path(job_dir).expanduser() / pages_subdir
    if not pages_dir.is_dir():
        raise FileNotFoundError(f"missing {pages_dir}")
    exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
    paths = sorted(p for p in pages_dir.iterdir() if p.suffix.lower() in exts)
    rows: list[tuple[Path, DeskewMeta]] = []
    for path in paths:
        meta = deskew_file(path, in_place=in_place, max_angle=max_angle, min_abs_angle=min_abs_angle)
        rows.append((path, meta))
    return rows
