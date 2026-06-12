"""PDF → per-page JPEG rasterization.

Vendored from transcription-shell ``pipeline/pdf_extract.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PDF_CACHE_DIRNAME = ".pdf-pages"


def cache_dir_for(pdf_path: Path, root: Path) -> Path:
    digest = hashlib.sha1(str(pdf_path.resolve()).encode("utf-8")).hexdigest()[:10]
    return root / PDF_CACHE_DIRNAME / f"{pdf_path.stem}-{digest}"


def extract_pdf_pages(
    pdf_path: Path,
    out_dir: Path,
    *,
    dpi: int = 300,
    jpeg_quality: int = 92,
) -> list[Path]:
    try:
        import fitz
    except ImportError as e:
        raise RuntimeError(
            "PDF support requires pymupdf: pip install -e ."
        ) from e

    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    try:
        n = len(doc)
        width = max(4, len(str(max(0, n - 1))))
        stem = pdf_path.stem
        existing = sorted(out_dir.glob(f"{stem}_page_*.jpg"))
        if len(existing) == n and n > 0:
            return existing

        out_paths: list[Path] = []
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            out = out_dir / f"{stem}_page_{i:0{width}d}.jpg"
            pix.pil_save(str(out), format="JPEG", quality=jpeg_quality)
            out_paths.append(out)
        return out_paths
    finally:
        doc.close()
