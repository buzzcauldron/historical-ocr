"""Detect embedded figures, save crops, and weave ``[fig:id]`` into protocol YAML."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from historical_ocr.config import Settings
from historical_ocr.figures.base import FigureExtractionReport, FigureResult


def _crops_dir_for(yaml_path: Path) -> Path:
    return yaml_path.parent / "figures"


def _crop_filename(image_stem: str, fig_id: str, ext: str = "png") -> str:
    safe_stem = image_stem.replace("/", "_").replace("\\", "_")
    return f"{safe_stem}_{fig_id}.{ext}"


def extract_figures_for_page(
    *,
    image_path: Path,
    lines_xml_path: Path | None,
    transcription_yaml_path: Path,
    settings: Settings | None = None,
) -> FigureExtractionReport:
    s = settings or Settings()
    if not s.figure_extract_enabled:
        return FigureExtractionReport(figures=[], backend="(disabled)")

    image_path = Path(image_path).expanduser().resolve()
    transcription_yaml_path = Path(transcription_yaml_path).expanduser().resolve()

    backend = (s.figure_extract_backend or "doclaynet").lower()
    if backend in ("doclaynet", "doclay", "yolo"):
        from historical_ocr.figures.doclay import detect_figures

        report = detect_figures(
            image_path,
            model_path_or_repo=s.figure_extract_model,
            min_confidence=s.figure_min_confidence,
            min_area_frac=s.figure_min_area_frac,
            classes_of_interest=tuple(s.figure_classes_list),
            device=s.figure_device,
        )
    else:
        return FigureExtractionReport(
            figures=[],
            backend="(unknown)",
            warnings=[f"unknown figure_extract_backend={backend!r}"],
        )

    if not report.figures:
        return report

    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow is required for figure cropping.") from e

    crops_dir = _crops_dir_for(transcription_yaml_path)
    crops_dir.mkdir(parents=True, exist_ok=True)
    pad = max(0, int(s.figure_pad_px))

    cropped: list[FigureResult] = []
    with Image.open(image_path) as im:
        w, h = im.size
        for f in report.figures:
            x0, y0, x1, y1 = f.bbox
            x0p = max(0, x0 - pad)
            y0p = max(0, y0 - pad)
            x1p = min(w, x1 + pad)
            y1p = min(h, y1 + pad)
            if x1p <= x0p or y1p <= y0p:
                continue
            crop = im.crop((x0p, y0p, x1p, y1p))
            fname = _crop_filename(image_path.stem, f.id)
            out_path = crops_dir / fname
            crop.save(out_path, format="PNG")
            cropped.append(replace(f, crop_path=out_path))

    report.figures = cropped

    from historical_ocr.figures.markers import insert_markers

    insert_markers(
        yaml_path=transcription_yaml_path,
        lines_xml_path=lines_xml_path,
        figures=cropped,
    )
    return report
