"""Page material CNN backend (print vs manuscript)."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.ml.page_cnn import MaterialLabel, checkpoint_summary, predict_image_path, torch_available


def available(model_path: Path | None) -> bool:
    return torch_available() and model_path is not None and model_path.is_file()


def classify_page(
    image_path: Path,
    *,
    model_path: Path,
    threshold: float = 0.5,
) -> tuple[MaterialLabel, float]:
    label, score = predict_image_path(model_path, image_path)
    if label == "print" and score < threshold:
        return "manuscript", 1.0 - score
    if label == "manuscript" and score < threshold:
        return "print", 1.0 - score
    return label, score


def describe(model_path: Path | None) -> str:
    if not torch_available():
        return "PyTorch not installed (pip install -e .)"
    if model_path is None or not model_path.is_file():
        return f"no model at {model_path or '(unset)'}"
    summary = checkpoint_summary(model_path)
    acc = summary.get("val_accuracy")
    acc_s = f"{acc:.1%}" if isinstance(acc, (int, float)) else "?"
    return f"{model_path.name} (val_acc={acc_s})"
