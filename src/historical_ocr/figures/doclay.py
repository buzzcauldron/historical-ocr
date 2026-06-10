"""DocLayNet-based figure detection via Ultralytics YOLO."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from historical_ocr.figures.base import FigureExtractionReport, FigureResult

DEFAULT_MODEL_REPO = "juliozhao/DocLayout-YOLO-DocLayNet"
DEFAULT_MODEL_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"

_DOCLAYNET_CLASSES = (
    "Caption",
    "Footnote",
    "Formula",
    "List-item",
    "Page-footer",
    "Page-header",
    "Picture",
    "Section-header",
    "Table",
    "Text",
    "Title",
)


def _resolve_weights(model_path_or_repo: str) -> str:
    p = Path(model_path_or_repo).expanduser()
    if p.is_file():
        return str(p)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise RuntimeError(
            "huggingface_hub required for figure-model downloads. "
            "Install with: pip install 'historical-ocr[figures]'"
        ) from e

    filename = os.environ.get("HISTORICAL_OCR_FIGURE_MODEL_FILENAME") or DEFAULT_MODEL_FILENAME
    return hf_hub_download(repo_id=model_path_or_repo, filename=filename)


def detect_figures(
    image_path: Path,
    *,
    model_path_or_repo: str = DEFAULT_MODEL_REPO,
    min_confidence: float = 0.4,
    min_area_frac: float = 0.01,
    classes_of_interest: Iterable[str] = ("Picture", "Table"),
    device: str = "cpu",
) -> FigureExtractionReport:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Ultralytics YOLO is required for figure detection. "
            "Install with: pip install 'historical-ocr[figures]'"
        ) from e
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow is required for figure detection.") from e

    image_path = Path(image_path).expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    weights = _resolve_weights(model_path_or_repo)
    model = YOLO(weights)

    with Image.open(image_path) as im:
        w, h = im.size
    page_area = float(max(1, w * h))
    coi = {c.lower() for c in classes_of_interest}

    results = model.predict(source=str(image_path), device=device, verbose=False)
    figures: list[FigureResult] = []
    warnings: list[str] = []

    if not results:
        warnings.append("YOLO returned no results")
        return FigureExtractionReport(figures=[], backend="doclaynet", warnings=warnings)

    r = results[0]
    names = getattr(r, "names", None) or {i: n for i, n in enumerate(_DOCLAYNET_CLASSES)}
    boxes = getattr(r, "boxes", None)
    if boxes is None:
        return FigureExtractionReport(figures=[], backend="doclaynet", warnings=["no boxes returned"])

    counter = 0
    xyxy = boxes.xyxy.tolist() if hasattr(boxes.xyxy, "tolist") else list(boxes.xyxy)
    cls_arr = boxes.cls.tolist() if hasattr(boxes.cls, "tolist") else list(boxes.cls)
    conf_arr = boxes.conf.tolist() if hasattr(boxes.conf, "tolist") else list(boxes.conf)

    for (x0, y0, x1, y1), cls_idx, conf in zip(xyxy, cls_arr, conf_arr):
        label = str(names.get(int(cls_idx), int(cls_idx)))
        if label.lower() not in coi:
            continue
        if float(conf) < min_confidence:
            continue
        bbox = (int(x0), int(y0), int(x1), int(y1))
        area_frac = max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / page_area
        if area_frac < min_area_frac:
            continue
        counter += 1
        figures.append(
            FigureResult(
                id=f"fig_{counter:02d}",
                bbox=bbox,
                label=label,
                confidence=float(conf),
            ),
        )

    return FigureExtractionReport(figures=figures, backend="doclaynet", warnings=warnings)
