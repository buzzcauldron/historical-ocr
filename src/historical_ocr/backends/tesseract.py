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
    "ell",
    "grc",
    "osd",
)

# histnews is an English/Antiqua LSTM fine-tune (start_model=eng, CA newspapers).
# Agbeti-Messan et al. 2026 (arXiv:2604.00725): generic/English Tesseract is
# competitive on Antiqua (~5% CER) but collapses on Fraktur (~21% CER). Do not
# prepend histnews onto Fraktur, blackletter, or non-Latin scripts.
_ANTIQUA_FINETUNE_LANGS = frozenset({"eng", "lat", "fra", "ita", "spa", "deu", "por", "nld"})
_SKIP_FINETUNE_LANGS = frozenset(
    {
        "frk",
        "deu_latf",
        "grc",
        "ell",
        "script/Greek",
        "script/Fraktur",
        "chi_sim",
        "chi_tra",
        "ara",
        "heb",
        "rus",
    }
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


def _install_finetune_tessdata(settings) -> Path | None:
    """Copy fine-tuned traineddata into models/tessdata for TESSDATA_PREFIX."""
    lang = getattr(settings, "tesseract_finetune_lang", None)
    path = getattr(settings, "tesseract_finetune_path", None)
    if not lang or not path:
        return None
    src = Path(path).expanduser()
    if not src.is_file():
        return None
    dest_dir = src.parent / "tessdata"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{lang}.traineddata"
    if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
        shutil.copy2(src, dest)
    return dest_dir


def finetune_applies_to(lang_bundle: str, *, finetune_lang: str = "histnews") -> bool:
    """Whether an Antiqua newspaper fine-tune should prepend this Tesseract bundle."""
    parts = langs_in_bundle(lang_bundle)
    if not parts:
        return False
    if parts & _SKIP_FINETUNE_LANGS:
        return False
    if finetune_lang and finetune_lang in parts:
        return True
    return bool(parts & _ANTIQUA_FINETUNE_LANGS)


def resolve_lang_bundle(lang_bundle: str, settings=None) -> str:
    """Prepend fine-tuned Antiqua lang when traineddata is installed and compatible.

    histnews is skipped for Fraktur (``frk``, ``deu_latf``) and Greek (``grc``,
    ``ell``) bundles so the English newspaper LSTM cannot dominate those scripts.
    """
    if settings is None:
        return lang_bundle
    lang = getattr(settings, "tesseract_finetune_lang", None)
    path = getattr(settings, "tesseract_finetune_path", None)
    if not lang or not path or not Path(path).expanduser().is_file():
        return lang_bundle
    if not finetune_applies_to(lang_bundle, finetune_lang=str(lang)):
        return lang_bundle
    parts = [p.strip() for p in lang_bundle.split("+") if p.strip()]
    if lang not in parts:
        parts.insert(0, str(lang))
    return "+".join(parts)


def configure_from_settings(settings) -> None:
    prefix = settings.tessdata_prefix
    finetune_dir = _install_finetune_tessdata(settings)
    if finetune_dir is not None and prefix is None:
        prefix = finetune_dir
    configure(
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=prefix,
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


def build_config(
    *,
    psm: int,
    char_blacklist: str | None = None,
    char_whitelist: str | None = None,
) -> str:
    """Assemble Tesseract CLI config (PSM + optional character filters)."""
    parts = [f"--psm {psm}"]
    if char_whitelist:
        parts.append(f"-c tessedit_char_whitelist={char_whitelist}")
    elif char_blacklist:
        parts.append(f"-c tessedit_char_blacklist={char_blacklist}")
    return " ".join(parts)


def ensure_ready(lang_bundle: str, *, settings=None) -> None:
    """Raise with install hint if tesseract or required langs are missing."""
    lang_bundle = resolve_lang_bundle(lang_bundle, settings)
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
