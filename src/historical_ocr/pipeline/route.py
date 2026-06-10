"""Route pages to manuscript vs print pipelines."""

from __future__ import annotations

from historical_ocr.models.manifest import JobManifest


def apply_routes(manifest: JobManifest, mode: str) -> str:
    if mode == "manuscript":
        for p in manifest.pages:
            p.route = "manuscript"
        return "manuscript"

    if mode == "print":
        for p in manifest.pages:
            p.route = "print"
        return "print"

    suggested = "manuscript"
    if manifest.fingerprint and manifest.fingerprint.suggested_material == "print":
        suggested = "print"

    for p in manifest.pages:
        p.route = suggested  # type: ignore[assignment]
    return suggested
