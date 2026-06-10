"""Tesseract OCR backend — binary detection, config, and language packs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Traineddata stems used across diachronic print profiles (1500–present).
HISTORICAL_LANGS: tuple[str, ...] = (
    "eng",
    "lat",
    "frk",
    "deu",
    "deu_latf",
    "fra",
    "ita",
    "spa",
    "osd",
)

_LANG_SPLIT = re.compile(r"[+|]")


@dataclass(frozen=True)
class TesseractInfo:
    binary: str | None
    version: str | None
    tessdata_dir: str | None
    installed_langs: tuple[str, ...]


def binary_path() -> str | None:
    return shutil.which("tesseract") or os.environ.get("TESSERACT_CMD")


def available() -> bool:
    return binary_path() is not None


def _run_tesseract(args: list[str], *, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    cmd = binary_path()
    if not cmd:
        raise RuntimeError("tesseract not on PATH")
    return subprocess.run(
        [cmd, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_info() -> TesseractInfo:
    binary = binary_path()
    if not binary:
        return TesseractInfo(None, None, None, ())

    version = None
    proc = _run_tesseract(["--version"])
    if proc.stdout:
        version = proc.stdout.splitlines()[0].strip()

    tessdata = os.environ.get("TESSDATA_PREFIX")
    langs: list[str] = []
    proc = _run_tesseract(["--list-langs"])
    if proc.stdout:
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("List of"):
                langs.append(line)

    if not tessdata and langs:
        # Infer from common layouts when not set explicitly.
        for candidate in (
            Path("/opt/homebrew/share/tessdata"),
            Path("/usr/local/share/tessdata"),
            Path("/usr/share/tesseract-ocr/5/tessdata"),
            Path("/usr/share/tesseract-ocr/4.00/tessdata"),
            Path("/usr/share/tessdata"),
        ):
            if (candidate / f"{langs[0]}.traineddata").is_file():
                tessdata = str(candidate)
                break

    return TesseractInfo(binary, version, tessdata, tuple(langs))


def installed_lang_set() -> set[str]:
    return set(get_info().installed_langs)


def langs_in_bundle(lang_bundle: str) -> set[str]:
    return {p.strip() for p in _LANG_SPLIT.split(lang_bundle) if p.strip()}


def missing_langs(lang_bundle: str, *, installed: set[str] | None = None) -> list[str]:
    have = installed if installed is not None else installed_lang_set()
    return sorted(langs_in_bundle(lang_bundle) - have)


def historical_langs_missing(*, installed: set[str] | None = None) -> list[str]:
    have = installed if installed is not None else installed_lang_set()
    return [lang for lang in HISTORICAL_LANGS if lang not in have]


def configure(
    *,
    tesseract_cmd: str | Path | None = None,
    tessdata_prefix: str | Path | None = None,
) -> None:
    """Apply env + pytesseract settings before OCR calls."""
    import pytesseract

    cmd = str(tesseract_cmd) if tesseract_cmd else binary_path()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        os.environ.setdefault("TESSERACT_CMD", cmd)

    prefix = str(tessdata_prefix) if tessdata_prefix else os.environ.get("TESSDATA_PREFIX")
    if prefix:
        os.environ["TESSDATA_PREFIX"] = prefix


def configure_from_settings(settings) -> None:
    configure(
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    )


def describe(*, lang_bundle: str | None = None) -> str:
    info = get_info()
    if not info.binary:
        return "not on PATH — install tesseract (brew install tesseract tesseract-lang)"
    parts = [info.version or info.binary]
    if info.tessdata_dir:
        parts.append(f"tessdata={info.tessdata_dir}")
    if lang_bundle:
        missing = missing_langs(lang_bundle, installed=set(info.installed_langs))
        if missing:
            parts.append(f"missing langs: {', '.join(missing)}")
    return " · ".join(parts)


def ensure_ready(lang_bundle: str) -> None:
    """Raise with install hint if tesseract or required langs are missing."""
    if not available():
        raise RuntimeError(
            "tesseract not found on PATH. Install:\n"
            "  macOS:  brew install tesseract tesseract-lang\n"
            "  Debian: sudo apt install tesseract-ocr tesseract-ocr-eng "
            "tesseract-ocr-lat tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa",
        )
    missing = missing_langs(lang_bundle)
    if missing:
        raise RuntimeError(
            f"tesseract missing traineddata for: {', '.join(missing)}\n"
            "  macOS:  brew install tesseract-lang\n"
            "  Debian: sudo apt install tesseract-ocr-<lang> for each missing pack",
        )
