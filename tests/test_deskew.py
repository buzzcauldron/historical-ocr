"""Page deskew helpers."""

from __future__ import annotations

from PIL import Image, ImageDraw

from historical_ocr.image_tools.deskew import deskew_image


def _page_with_text(angle: float = 3.0) -> Image.Image:
    im = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(im)
    for y in range(30, 200, 24):
        draw.text((20, y), "Historical newspaper OCR deskew test", fill="black")
    return im.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")


def test_deskew_image_runs_without_error() -> None:
    out, meta = deskew_image(_page_with_text(2.5), min_abs_angle=0.2)
    assert out.size[0] > 0
    assert meta.method in ("projection", "opencv")
