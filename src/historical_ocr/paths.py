"""Install-aware path resolution for package data and project roots."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def package_dir() -> Path:
    """Directory containing the installed ``historical_ocr`` package."""
    return Path(__file__).resolve().parent


def document_types_print_dir() -> Path:
    """Built-in print document-type YAMLs (shipped inside the package)."""
    return package_dir() / "document_types" / "print"


def ocr_models_registry_dir() -> Path:
    """Built-in OCR stack registry YAMLs under document types."""
    return document_types_print_dir() / "models"


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Repo / working root for jobs, ``.env``, and optional sibling tools.

    Resolution order:
    1. ``HISTORICAL_OCR_ROOT`` / ``HISTORICAL_OCR_PROJECT_ROOT``
    2. Walk up from the package for a checkout with ``pyproject.toml``
    3. Current working directory
    """
    for key in ("HISTORICAL_OCR_ROOT", "HISTORICAL_OCR_PROJECT_ROOT"):
        raw = os.environ.get(key)
        if raw and str(raw).strip():
            return Path(raw).expanduser().resolve()

    # Editable / source-tree layout: …/repo/src/historical_ocr/paths.py
    src_layout = package_dir().parent.parent
    if (src_layout / "pyproject.toml").is_file() and (src_layout / "src" / "historical_ocr").is_dir():
        return src_layout

    # Installed layout: still allow finding a local checkout via CWD
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        if not (
            (candidate / "src" / "historical_ocr").is_dir()
            or (candidate / "historical_ocr").is_dir()
        ):
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if 'name = "historical-ocr"' in text or "name = 'historical-ocr'" in text:
            return candidate

    return cwd
