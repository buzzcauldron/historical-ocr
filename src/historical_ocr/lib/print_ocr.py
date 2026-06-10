"""Printed page text extraction.

Vendored from research-party ``cli/bib_pdf_ocr.py``; enhanced with bib-ocr
preprocessing and optional density-guided PDF targeting.
"""

from __future__ import annotations

from pathlib import Path

_MIN_CHARS_FOR_OCR_FALLBACK = 80


def ocr_image(
    image: Path,
    *,
    lang: str = "lat+frk+eng",
    settings=None,
    bib_preprocess: bool = True,
) -> str:
    from historical_ocr.backends import tesseract as tess_backend
    from historical_ocr.ocr.preprocess import prepare_for_tesseract
    from PIL import Image

    if settings is not None:
        tess_backend.configure_from_settings(settings)
        bib_preprocess = getattr(settings, "bib_preprocess", bib_preprocess)
    tess_backend.ensure_ready(lang)

    import pytesseract

    with Image.open(image) as im:
        pil = im.convert("RGB")
        if bib_preprocess:
            pil = prepare_for_tesseract(pil)
        return pytesseract.image_to_string(pil, lang=lang).strip()


def extract_pdf_page_text(
    pdf_path: Path,
    page_idx: int,
    *,
    lang: str = "lat+frk+eng",
    ocr_dpi: int = 300,
    bib_preprocess: bool = True,
    settings=None,
) -> str:
    from pypdf import PdfReader

    if settings is not None:
        bib_preprocess = getattr(settings, "bib_preprocess", bib_preprocess)
        ocr_dpi = settings.pdf_dpi if hasattr(settings, "pdf_dpi") else ocr_dpi

    reader = PdfReader(str(pdf_path))
    try:
        text = (reader.pages[page_idx].extract_text() or "").strip()
    except Exception:
        text = ""

    if len(text) >= _MIN_CHARS_FOR_OCR_FALLBACK:
        return text

    try:
        from historical_ocr.backends import tesseract as tess_backend
        from historical_ocr.ocr.preprocess import prepare_for_tesseract
        from pdf2image import convert_from_path

        tess_backend.ensure_ready(lang)
        import pytesseract

        images = convert_from_path(
            str(pdf_path),
            first_page=page_idx + 1,
            last_page=page_idx + 1,
            dpi=ocr_dpi,
        )
        if images:
            pil = images[0]
            if bib_preprocess:
                pil = prepare_for_tesseract(pil.convert("RGB"))
            return pytesseract.image_to_string(pil, lang=lang, config="--psm 6").strip()
    except Exception:
        pass
    return text


def pdf_ocr_target_pages(
    pdf_path: Path,
    *,
    settings=None,
) -> set[int] | None:
    """Density/sparsity map of PDF pages that benefit from OCR fallback."""
    if settings is not None and not getattr(settings, "pdf_density_ocr", True):
        return None
    from historical_ocr.lib.bib_density import pages_needing_ocr

    return pages_needing_ocr(pdf_path, min_embedded_chars=_MIN_CHARS_FOR_OCR_FALLBACK)


def save_pdf_density_artifact(
    pdf_path: Path,
    dest: Path,
    *,
    title: str = "Citation density",
) -> bool:
    """Write density heatmap PNG when matplotlib is available."""
    try:
        from historical_ocr.lib.bib_density import page_density

        density = page_density(pdf_path)
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        n_pages, bands = density.shape
        fig, ax_map = plt.subplots(figsize=(max(6, n_pages * 0.25), 4))
        vmax = float(density.max()) or 1.0
        norm = mcolors.PowerNorm(gamma=0.5, vmin=0, vmax=vmax)
        ax_map.imshow(
            density.T,
            aspect="auto",
            cmap="YlOrRd",
            norm=norm,
            origin="upper",
            interpolation="nearest",
        )
        ax_map.set_xlabel("Page")
        ax_map.set_ylabel("Vertical band")
        ax_map.set_title(title)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(dest), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return True
    except Exception:
        return False
