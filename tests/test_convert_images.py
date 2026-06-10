"""Image converter (synced with transcription-shell)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from historical_ocr.image_tools.convert import convert_file, find_images, normalize_page_image


def test_find_images_flat_and_recurse(tmp_path: Path) -> None:
    a = tmp_path / "a.tif"
    sub = tmp_path / "sub"
    sub.mkdir()
    b = sub / "b.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(a)
    Image.new("RGB", (8, 8), (4, 5, 6)).save(b)

    assert len(find_images([tmp_path], recurse=False)) == 1
    assert len(find_images([tmp_path], recurse=True)) == 2


def test_normalize_page_image_resizes(tmp_path: Path) -> None:
    src = tmp_path / "big.jpg"
    dst = tmp_path / "out.jpg"
    Image.new("RGB", (4000, 2000), (200, 200, 200)).save(src, quality=95)

    meta = normalize_page_image(src, dst, max_width=1000, max_pixels=2_000_000)
    assert meta.resized
    assert meta.width <= 1000
    assert meta.output.is_file()


def test_convert_file_dry_run(tmp_path: Path) -> None:
    src = tmp_path / "scan.tiff"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(src)

    status, msg = convert_file(src, dry_run=True, max_width=32)
    assert status == "dry-run"
    assert "scan" in msg
