"""Image conversion and PAGE-XML coordinate scaling.

Canonical logic synced from transcription-shell ``image_tools/convert.py``.
historical-ocr adds ``max_pixels`` guardrails and ``normalize_page_image`` for ingest.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

CONVERTIBLE = frozenset({".tif", ".tiff", ".bmp", ".webp", ".gif", ".pcx", ".ppm", ".pgm", ".pbm", ".ico"})
PASSTHROUGH = frozenset({".jpg", ".jpeg", ".png"})
ALL_IMAGE_EXTS = CONVERTIBLE | PASSTHROUGH

OutputFormat = Literal["jpeg", "png"]


@dataclass(frozen=True)
class ImageNormalizeMeta:
    source: Path
    output: Path
    orig_width: int
    orig_height: int
    width: int
    height: int
    resized: bool
    format: str


def find_images(sources: list[Path], *, recurse: bool = False) -> list[Path]:
    images: list[Path] = []
    for src in sources:
        if src.is_dir():
            pattern = "**/*" if recurse else "*"
            for p in sorted(src.glob(pattern)):
                if p.is_file() and p.suffix.lower() in ALL_IMAGE_EXTS:
                    images.append(p)
        elif src.is_file():
            images.append(src)
    return images


def _scale_points(points_str: str, sx: float, sy: float) -> str:
    out: list[str] = []
    for tok in points_str.split():
        if "," not in tok:
            out.append(tok)
            continue
        x, _, y = tok.partition(",")
        out.append(f"{round(float(x) * sx)},{round(float(y) * sy)}")
    return " ".join(out)


def scale_paired_xml(
    src_img: Path,
    dst_img: Path,
    orig_w: int,
    orig_h: int,
    new_w: int,
    new_h: int,
    *,
    force: bool = False,
) -> bool:
    """Scale PAGE XML coords to match a resized image. Returns True if written."""
    xml_src = src_img.with_suffix(".xml")
    if not xml_src.is_file():
        return False
    xml_dst = dst_img.with_suffix(".xml")
    if xml_dst.is_file() and not force:
        return False

    sx = new_w / orig_w
    sy = new_h / orig_h
    tree = ET.parse(str(xml_src))
    root = tree.getroot()

    page = root.find(".//{*}Page")
    if page is not None:
        page.set("imageWidth", str(new_w))
        page.set("imageHeight", str(new_h))
        page.set("imageFilename", dst_img.name)

    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag in ("Coords", "Baseline"):
            pts = el.get("points", "")
            if pts:
                el.set("points", _scale_points(pts, sx, sy))

    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    if ns:
        ET.register_namespace("", ns)
    tree.write(str(xml_dst), xml_declaration=True, encoding="unicode")
    return True


def _target_path(src: Path, out_dir: Path | None, fmt: OutputFormat) -> Path:
    ext = ".jpg" if fmt == "jpeg" else ".png"
    base = out_dir if out_dir else src.parent
    return base / (src.stem + ext)


def _cucim_available() -> bool:
    try:
        import cucim.skimage.transform  # noqa: F401
        import cupy  # noqa: F401

        return True
    except ImportError:
        return False


def _resize(
    img: Image.Image,
    max_width: int | None,
    max_height: int | None,
    *,
    max_pixels: int | None = None,
    use_cucim: bool = False,
) -> Image.Image:
    w, h = img.size
    if max_pixels and w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        w, h = int(w * scale), int(h * scale)
    if max_width and w > max_width:
        h = int(h * max_width / w)
        w = max_width
    if max_height and h > max_height:
        w = int(w * max_height / h)
        h = max_height
    if (w, h) == img.size:
        return img

    if use_cucim and _cucim_available():
        import cupy as cp
        import cucim.skimage.transform as cst
        import numpy as np

        arr = np.array(img.convert("RGB") if img.mode not in ("RGB", "L") else img)
        gpu = cp.asarray(arr)
        out_shape = (h, w) if arr.ndim == 2 else (h, w, arr.shape[2])
        resized = cp.asnumpy(
            cst.resize(gpu, out_shape, anti_aliasing=True, preserve_range=True).astype(cp.uint8),
        )
        return Image.fromarray(resized)

    return img.resize((w, h), Image.LANCZOS)


def _prepare_and_resize(
    img: Image.Image,
    *,
    fmt: OutputFormat,
    max_width: int | None,
    max_height: int | None,
    max_pixels: int | None,
    use_cucim: bool,
) -> tuple[Image.Image, tuple[int, int]]:
    if fmt == "jpeg" and img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode not in ("RGB", "L") and fmt == "jpeg":
        img = img.convert("RGB")

    orig_size = img.size
    img = _resize(img, max_width, max_height, max_pixels=max_pixels, use_cucim=use_cucim)
    return img, orig_size


def image_within_limits(
    src: Path,
    *,
    max_width: int | None,
    max_height: int | None,
    max_pixels: int | None,
    fmt: OutputFormat = "jpeg",
) -> bool:
    """True when ``src`` is already a suitable JPEG within size caps (skip re-encode)."""
    if src.suffix.lower() not in (".jpg", ".jpeg"):
        return False
    try:
        with Image.open(src) as im:
            if im.format not in ("JPEG", "JPG"):
                return False
            w, h = im.size
    except OSError:
        return False
    if max_pixels and w * h > max_pixels:
        return False
    if max_width and w > max_width:
        return False
    if max_height and h > max_height:
        return False
    return fmt == "jpeg"


def normalize_page_image(
    src: Path,
    dst: Path,
    *,
    fmt: OutputFormat = "jpeg",
    max_width: int | None = 3000,
    max_height: int | None = None,
    max_pixels: int | None = 16_000_000,
    quality: int = 90,
    scale_xml: bool = True,
    force: bool = False,
    use_cucim: bool = False,
    optimize: bool = True,
) -> ImageNormalizeMeta:
    """Resize/convert a page image for pipeline ingest. Returns size metadata."""
    dst = dst.with_suffix(".jpg" if fmt == "jpeg" else ".png")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if (
        not force
        and image_within_limits(
            src,
            max_width=max_width,
            max_height=max_height,
            max_pixels=max_pixels,
            fmt=fmt,
        )
    ):
        if src.resolve() != dst.resolve():
            import shutil

            shutil.copy2(src, dst)
        with Image.open(dst) as im:
            w, h = im.size
        return ImageNormalizeMeta(
            source=src,
            output=dst,
            orig_width=w,
            orig_height=h,
            width=w,
            height=h,
            resized=False,
            format=fmt,
        )

    if dst.is_file() and not force and src.resolve() == dst.resolve():
        with Image.open(dst) as im:
            w, h = im.size
        return ImageNormalizeMeta(
            source=src,
            output=dst,
            orig_width=w,
            orig_height=h,
            width=w,
            height=h,
            resized=False,
            format=fmt,
        )

    with Image.open(src) as opened:
        img, orig_size = _prepare_and_resize(
            opened,
            fmt=fmt,
            max_width=max_width,
            max_height=max_height,
            max_pixels=max_pixels,
            use_cucim=use_cucim,
        )
        save_kwargs: dict = {"optimize": optimize}
        if fmt == "jpeg":
            save_kwargs["quality"] = quality
        img.save(dst, format=fmt.upper(), **save_kwargs)
        new_size = img.size

    if scale_xml and new_size != orig_size:
        scale_paired_xml(src, dst, orig_size[0], orig_size[1], new_size[0], new_size[1], force=force)

    return ImageNormalizeMeta(
        source=src,
        output=dst,
        orig_width=orig_size[0],
        orig_height=orig_size[1],
        width=new_size[0],
        height=new_size[1],
        resized=new_size != orig_size,
        format=fmt,
    )


def convert_file(
    src: Path,
    *,
    out_dir: Path | None = None,
    fmt: OutputFormat = "jpeg",
    max_width: int | None = 3000,
    max_height: int | None = None,
    max_pixels: int | None = 16_000_000,
    quality: int = 90,
    keep_original: bool = False,
    force: bool = False,
    dry_run: bool = False,
    scale_xml: bool = True,
    use_cucim: bool = False,
) -> tuple[str, str]:
    """Convert one image. Returns (status, message). Status: converted | skipped | error."""
    src_ext = src.suffix.lower()
    is_passthrough = src_ext in PASSTHROUGH
    target_ext = ".jpg" if fmt == "jpeg" else ".png"

    if is_passthrough and keep_original and src_ext == target_ext:
        return "skipped", f"{src.name} (already {fmt})"

    dst = _target_path(src, out_dir, fmt)
    if dst.is_file() and not force and not (is_passthrough and src.resolve() == dst.resolve()):
        return "skipped", f"{src.name} → {dst} (exists)"

    if dry_run:
        return "dry-run", f"{src.name} → {dst.name}"

    try:
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)

        with Image.open(src) as opened:
            img, orig_size = _prepare_and_resize(
                opened,
                fmt=fmt,
                max_width=max_width,
                max_height=max_height,
                max_pixels=max_pixels,
                use_cucim=use_cucim,
            )
            save_kwargs: dict = {"optimize": True}
            if fmt == "jpeg":
                save_kwargs["quality"] = quality
            img.save(dst, format=fmt.upper(), **save_kwargs)
            new_size = img.size

        xml_note = ""
        if scale_xml and new_size != orig_size:
            if scale_paired_xml(
                src,
                dst,
                orig_size[0],
                orig_size[1],
                new_size[0],
                new_size[1],
                force=force,
            ):
                xml_note = " + XML scaled"

        size_kb = dst.stat().st_size // 1024
        resize_note = (
            f" → resized {orig_size[0]}×{orig_size[1]} to {new_size[0]}×{new_size[1]}"
            if new_size != orig_size
            else ""
        )
        return "converted", f"{src.name}{resize_note} → {dst.name} ({size_kb} KB){xml_note}"

    except Exception as exc:
        return "error", f"{src.name}: {exc}"
