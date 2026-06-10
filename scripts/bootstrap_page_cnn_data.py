#!/usr/bin/env python3
"""Copy seed images into data/page_cnn/{print,manuscript}/ for CNN training."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from historical_ocr.lib.fetch import fetch_assets_from_url  # noqa: E402

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
_MANUSCRIPT_IIIF = (
    "https://www.bl.uk/iiif-metadata/manifests/ark:/81055/vdc_000000046826.1/manifest.json"
)


def _is_image(path: Path) -> bool:
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        return False
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def _copy_glob(folder: Path, dest_dir: Path, prefix: str) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for i, src in enumerate(sorted(folder.iterdir())):
        if not _is_image(src):
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{prefix}{i:03d}{src.suffix.lower()}"
        if dest.is_file():
            continue
        shutil.copy2(src, dest)
        n += 1
    return n


def _fetch_manuscript_iiif(dest_dir: Path, *, limit: int = 5) -> int:
    tmp = dest_dir / "_fetched"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        assets = fetch_assets_from_url(_MANUSCRIPT_IIIF, tmp, limit=limit)
    except Exception as exc:
        print(f"warn: IIIF fetch failed ({exc})")
        shutil.rmtree(tmp, ignore_errors=True)
        return 0
    n = 0
    for i, src in enumerate(assets):
        if not _is_image(src):
            continue
        dest = dest_dir / f"bl_ms_{i:03d}{src.suffix.lower()}"
        shutil.copy2(src, dest)
        n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    return n


def _synth_manuscript_pages(dest_dir: Path, *, count: int = 5, seed: int = 42) -> int:
    """Placeholder manuscript pages when no labeled scans are available locally."""
    import random

    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        im = Image.new("RGB", (1200, 1600), (235, 220, 190))
        draw = ImageDraw.Draw(im)
        y = 120
        while y < 1500:
            x = rng.randint(80, 140)
            while x < 1050:
                w = rng.randint(30, 220)
                h = rng.randint(4, 18)
                draw.rectangle((x, y, x + w, y + h), fill=(25, 20, 15))
                x += w + rng.randint(8, 40)
            y += rng.randint(28, 52)
        for _ in range(rng.randint(40, 80)):
            x0, y0 = rng.randint(0, 1199), rng.randint(0, 1599)
            draw.line(
                (x0, y0, x0 + rng.randint(-80, 80), y0 + rng.randint(-12, 12)),
                fill=(15, 10, 8),
                width=rng.randint(1, 3),
            )
        dest = dest_dir / f"synth_ms_{i:03d}.jpg"
        im.save(dest, quality=90)
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("data/page_cnn"),
        help="Output dataset root (default: data/page_cnn)",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = args.out.expanduser().resolve()
    print_dir = out / "print"
    ms_dir = out / "manuscript"
    n_print = 0
    n_ms = 0

    n_print += _copy_glob(root / "jobs" / "scrape-iiif" / "pages", print_dir, "ia_")
    n_print += _copy_glob(root / "jobs" / "_test_print" / "pages", print_dir, "fixture_")
    n_print += _copy_glob(root / "jobs" / "_pytest_print" / "pages", print_dir, "pytest_")
    shell = root.parent / "transcription-shell"
    bench = shell / "vendor" / "transcription-protocol" / "benchmark" / "images" / "BM-EM-001"
    n_ms += _copy_glob(bench, ms_dir, "bm_")

    if len(list(ms_dir.glob("*"))) < 3:
        print(f"fetching manuscript pages from {_MANUSCRIPT_IIIF}")
        n_ms += _fetch_manuscript_iiif(ms_dir, limit=5)

    if len(list(ms_dir.glob("*"))) < 3:
        print("warn: using synthetic manuscript placeholders — replace with real labeled scans")
        n_ms += _synth_manuscript_pages(ms_dir, count=5)

    print(f"print: {n_print} new  → {print_dir}")
    print(f"manuscript: {n_ms} new  → {ms_dir}")
    print(f"total on disk: {len(list(print_dir.glob('*'))) if print_dir.is_dir() else 0} print, "
          f"{len(list(ms_dir.glob('*'))) if ms_dir.is_dir() else 0} manuscript")
    print()
    print("For large print corpora + OCRDatasets manuscripts:")
    print("  historical-ocr cnn sources")
    print("  historical-ocr cnn fetch --source ocr-quality --source ocr-pdf-degraded")
    print("  historical-ocr cnn fetch --all-hf   # includes pixparse PDF collections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
