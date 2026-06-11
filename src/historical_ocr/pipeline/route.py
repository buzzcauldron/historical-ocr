"""Route pages to the print OCR pipeline (print-only project)."""

from __future__ import annotations

from historical_ocr.models.manifest import JobManifest


def apply_routes(
    manifest: JobManifest,
    mode: str,
    *,
    job_root=None,
    settings=None,
    log_fn=None,
) -> str:
    del mode, job_root, settings  # print-only; kept for call-site compatibility
    for p in manifest.pages:
        p.route = "print"
    if log_fn:
        for p in manifest.pages:
            log_fn(f"route: {p.page_id} → print")
    return "print"
