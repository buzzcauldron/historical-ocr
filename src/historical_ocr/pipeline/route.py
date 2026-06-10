"""Route pages to manuscript vs print pipelines."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.backends import page_cnn as cnn_backend
from historical_ocr.config import Settings
from historical_ocr.models.manifest import JobManifest


def apply_routes(
    manifest: JobManifest,
    mode: str,
    *,
    job_root: Path | None = None,
    settings: Settings | None = None,
    log_fn=None,
) -> str:
    if mode == "manuscript":
        for p in manifest.pages:
            p.route = "manuscript"
        return "manuscript"

    if mode == "print":
        for p in manifest.pages:
            p.route = "print"
        return "print"

    s = settings or Settings()
    model_path = s.page_cnn_model.expanduser().resolve() if s.page_cnn_model else None
    use_cnn = cnn_backend.available(model_path) and job_root is not None

    if use_cnn:
        routes: set[str] = set()
        for p in manifest.pages:
            image = job_root / p.image_path
            label, score = cnn_backend.classify_page(
                image,
                model_path=model_path,  # type: ignore[arg-type]
                threshold=s.page_cnn_threshold,
            )
            p.route = label  # type: ignore[assignment]
            p.fingerprint_score = score
            routes.add(label)
            if log_fn:
                log_fn(f"route-cnn: {p.page_id} → {label} ({score:.2f})")
        if routes == {"print"}:
            return "print"
        if routes == {"manuscript"}:
            return "manuscript"
        return "mixed"

    suggested = "manuscript"
    if manifest.fingerprint and manifest.fingerprint.suggested_material == "print":
        suggested = "print"

    for p in manifest.pages:
        p.route = suggested  # type: ignore[assignment]
    return suggested
