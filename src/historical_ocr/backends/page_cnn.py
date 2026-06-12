"""Page material CNN backend (print vs manuscript) — lazy torch import."""

from __future__ import annotations

from pathlib import Path


def _ml():
    from historical_ocr.ml.page_cnn import (
        MaterialLabel,
        checkpoint_summary,
        predict_image_path,
        torch_available,
    )
    return MaterialLabel, checkpoint_summary, predict_image_path, torch_available


def available(model_path: Path | None) -> bool:
    try:
        _, _, _, torch_available = _ml()
        return torch_available() and model_path is not None and model_path.is_file()
    except ImportError:
        return False


def classify_page(
    image_path: Path,
    *,
    model_path: Path,
    threshold: float = 0.5,
) -> tuple[str, float]:
    _, _, predict_image_path, _ = _ml()
    label, score = predict_image_path(model_path, image_path)
    if score < threshold:
        return ("manuscript" if label == "print" else "print"), 1.0 - score
    return label, score


def describe(model_path: Path | None) -> str:
    try:
        _, checkpoint_summary, _, torch_available = _ml()
    except ImportError:
        return "torch not installed — pip install -e '.[ml]'"
    if not torch_available():
        return "torch not installed — pip install -e '.[ml]'"
    if model_path is None or not model_path.is_file():
        return f"no model at {model_path or '(unset)'}"
    summary = checkpoint_summary(model_path)
    acc = summary.get("val_accuracy")
    acc_s = f"{acc:.1%}" if isinstance(acc, (int, float)) else "?"
    return f"{model_path.name} (val_acc={acc_s})"
