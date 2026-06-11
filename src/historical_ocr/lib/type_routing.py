"""Print doc_type hints from fingerprint scans and page image probes."""

from __future__ import annotations

import json
from pathlib import Path

from historical_ocr.models.manifest import FingerprintSummary, JobManifest


def fingerprint_era_hint(summary: FingerprintSummary | None) -> str | None:
    """Map type-case fingerprint summary to suggest_print_doc_type era hint."""
    if summary is None:
        return None
    blob = json.dumps(summary.type_case_matches, default=str).lower()
    if "fraktur" in blob or "german" in blob:
        return "fraktur"
    if "blackletter" in blob or "secretary" in blob or "eebo" in blob:
        return "blackletter"
    if "humanist" in blob or "roman" in blob or "antiqua" in blob:
        return "antiqua"
    if summary.suggested_material == "print" and summary.type_case_matches:
        top = summary.type_case_matches[0]
        if isinstance(top, dict):
            for key in ("era", "typeface", "script", "name", "font"):
                val = str(top.get(key) or "").lower()
                if val:
                    return val
    return None


def load_fingerprint_summary(scan_dir: Path) -> FingerprintSummary | None:
    fp_json = Path(scan_dir).expanduser() / "fingerprints.json"
    if not fp_json.is_file():
        return None
    try:
        data = json.loads(fp_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    matches: list[dict] = []
    if isinstance(data, list):
        matches = [m for m in data if isinstance(m, dict)]
    elif isinstance(data, dict):
        for key in ("matches", "type_cases", "fingerprints", "results"):
            block = data.get(key)
            if isinstance(block, list):
                matches = [m for m in block if isinstance(m, dict)]
                break
        if not matches and data:
            matches = [data]

    material = "print" if matches else "unknown"
    return FingerprintSummary(
        job_dir=str(scan_dir),
        type_case_matches=matches,
        suggested_material=material,  # type: ignore[arg-type]
    )


def image_typeface_hint(image_path: Path, *, lang: str = "eng") -> str | None:
    """Fast dual-lang probe: fraktur/blackletter vs roman on a downscaled page."""
    try:
        from PIL import Image, ImageOps
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return None

    image_path = image_path.expanduser().resolve()
    if not image_path.is_file():
        return None

    with Image.open(image_path) as im:
        pil = ImageOps.autocontrast(im.convert("L")).convert("RGB")
        w, h = pil.size
        scale = min(1.0, 900 / max(w, h))
        if scale < 1.0:
            pil = pil.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    def _mean_conf(bundle: str) -> float:
        try:
            data = pytesseract.image_to_data(
                pil,
                lang=bundle,
                config="--psm 3",
                output_type=Output.DICT,
            )
        except Exception:
            return 0.0
        confs = []
        for c in data.get("conf", []):
            try:
                v = float(c)
            except (TypeError, ValueError):
                continue
            if v >= 0:
                confs.append(v)
        return sum(confs) / len(confs) if confs else 0.0

    eng_conf = _mean_conf("eng")
    frk_conf = _mean_conf("frk+eng")
    lat_conf = _mean_conf("lat+eng")
    best = max(frk_conf, lat_conf)
    if best >= eng_conf + 8.0 and frk_conf >= lat_conf:
        return "fraktur"
    if lat_conf >= eng_conf + 8.0:
        return "blackletter"
    if eng_conf >= 75.0:
        return "antiqua"
    return None


def page_type_hint(
    image_path: Path,
    manifest: JobManifest,
    *,
    fingerprint_era: str | None = None,
) -> str | None:
    """Combine job fingerprint with per-page image probe."""
    if fingerprint_era:
        return fingerprint_era
    if manifest.fingerprint:
        fp = fingerprint_era_hint(manifest.fingerprint)
        if fp:
            return fp
    return image_typeface_hint(image_path)


def doc_type_from_hints(
    *,
    manifest: JobManifest,
    language: str | None,
    fingerprint_era: str | None = None,
    image_era: str | None = None,
) -> str:
    from historical_ocr.document_types.print_types import suggest_print_doc_type

    era = image_era or fingerprint_era or fingerprint_era_hint(manifest.fingerprint)
    return suggest_print_doc_type(
        manifest=manifest,
        language=language,
        fingerprint_era=era,
    )
