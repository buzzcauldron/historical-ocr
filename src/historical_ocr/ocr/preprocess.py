"""Image preprocessing before Tesseract (per doc_type spec).

``prepare_for_tesseract`` follows the bib-ocr / witchofthewires/biblio pipeline
(invert + contrast) used for scanned bibliography pages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def prepare_for_tesseract(
    image: Image.Image,
    *,
    invert: bool = True,
    contrast: float = 2.0,
    rotate_degrees: float = 0.0,
    binarise: bool = False,
) -> Image.Image:
    """Bib-ocr style preprocessing for dark-text-on-light scans."""
    if image.mode == "RGBA":
        r, g, b, _ = image.split()
        image = Image.merge("RGB", (r, g, b))
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    if invert:
        image = ImageOps.invert(image.convert("RGB"))

    image = ImageEnhance.Contrast(image).enhance(contrast)

    if binarise:
        image = image.convert("L").point(lambda x: 0 if x < 128 else 255, "1")

    if rotate_degrees:
        image = image.rotate(-rotate_degrees, Image.NEAREST, expand=True)

    return image


def preprocess_for_ocr(image: Path, options: dict[str, Any]) -> Image.Image:
    with Image.open(image) as im:
        out = im.convert("RGB")

    if options.get("bib_preprocess"):
        return prepare_for_tesseract(
            out,
            invert=bool(options.get("invert", True)),
            contrast=float(options.get("contrast", 2.0)),
            binarise=bool(options.get("binarise", False)),
        )

    if options.get("grayscale"):
        out = ImageOps.grayscale(out).convert("RGB")
    if options.get("invert"):
        out = ImageOps.invert(out.convert("RGB"))
    if options.get("autocontrast"):
        out = ImageOps.autocontrast(out)
    if options.get("denoise"):
        out = out.filter(ImageFilter.MedianFilter(size=3))
    if options.get("unsharp"):
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))
    if options.get("sharpen"):
        out = out.filter(ImageFilter.SHARPEN)
    contrast = options.get("contrast")
    if contrast is not None:
        out = ImageEnhance.Contrast(out).enhance(float(contrast))
    if options.get("binarise"):
        out = out.convert("L").point(lambda x: 0 if x < 128 else 255, "1")
    return out
