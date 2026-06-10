"""Print document-type loader (mirrors transcription-shell document_types.py)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from historical_ocr.config import Settings

if TYPE_CHECKING:
    from historical_ocr.models.manifest import JobManifest
from historical_ocr.document_types.era_chronology import infer_publication_year
from historical_ocr.document_types.language_matrix import resolve_doc_type_for_language_year
from historical_ocr.document_types.languages import normalize_print_language
from historical_ocr.ocr.model_registry import select_ocr_stack

_ENV_RE = re.compile(r"\$\{(\w+)\}")

NormalizationMode = Literal["diplomatic", "normalized", "modern"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _builtin_dirs() -> list[Path]:
    return [
        _repo_root() / "document_types" / "print",
    ]


def _expand_env(val: str) -> str:
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), val)


@dataclass
class PrintDocumentTypeSpec:
    name: str
    language: str = ""
    era: str = ""
    era_range: str = ""
    script: str = ""
    typeface: str = ""

    ocr_engine: str = "tesseract"
    ocr_model: str | None = None
    tesseract_lang: str = "lat+frk+eng"
    tesseract_psm: int = 6

    layout_backend: str = "tesseract"
    ocr_combination: str = "tesseract_then_clean"
    normalization_mode: NormalizationMode = "normalized"

    shell_doc_type: str | None = None
    shell_htr_combination: str = "tesseract_htr"
    shell_lineation: str = "kraken"

    preprocess: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    _search_dirs: list[Path] = field(default_factory=list, repr=False)

    @property
    def clean_print(self) -> bool:
        return self.normalization_mode != "diplomatic"

    @property
    def clean_variants(self) -> bool:
        return self.normalization_mode == "modern"


def _parse_spec(name: str, raw: dict[str, Any], search_dirs: list[Path]) -> PrintDocumentTypeSpec:
    ocr = raw.get("ocr") or {}
    layout = raw.get("layout") or {}
    norm = raw.get("normalization") or {}
    shell = raw.get("shell") or {}
    if isinstance(norm, str):
        norm = {"mode": norm}
    return PrintDocumentTypeSpec(
        name=name,
        language=str(raw.get("language", "")),
        era=str(raw.get("era", "")),
        era_range=str(raw.get("era_range", raw.get("era", ""))),
        script=str(raw.get("script", "")),
        typeface=str(raw.get("typeface", "")),
        ocr_engine=str(ocr.get("engine", ocr.get("primary", "tesseract"))),
        ocr_model=ocr.get("model"),
        tesseract_lang=str(ocr.get("lang", "lat+frk+eng")),
        tesseract_psm=int(ocr.get("psm", 6)),
        layout_backend=str(layout.get("backend", "tesseract")),
        ocr_combination=str(raw.get("ocr_combination", "tesseract_then_clean")),
        normalization_mode=str(norm.get("mode", "normalized")),  # type: ignore[arg-type]
        shell_doc_type=shell.get("doc_type"),
        shell_htr_combination=str(shell.get("htr_combination", "tesseract_htr")),
        shell_lineation=str(shell.get("lineation", "kraken")),
        preprocess=dict(ocr.get("preprocess") or {}),
        notes=str(raw.get("notes", "")).strip(),
        _search_dirs=search_dirs,
    )


def _search_paths(name: str, extra_dirs: list[Path] | None = None) -> list[Path]:
    dirs = list(extra_dirs or []) + _builtin_dirs()
    if env := os.environ.get("HISTORICAL_OCR_PRINT_TYPES_DIR"):
        dirs.insert(0, Path(env).expanduser())
    out: list[Path] = []
    for d in dirs:
        cand = d / f"{name}.yaml"
        if cand.is_file():
            out.append(cand)
    return out


def load_print_doc_type(
    name: str,
    *,
    extra_dirs: list[Path] | None = None,
) -> PrintDocumentTypeSpec:
    paths = _search_paths(name, extra_dirs)
    if not paths:
        raise FileNotFoundError(
            f"Print document type '{name}' not found. "
            f"Searched: document_types/print/{name}.yaml",
        )
    path = paths[0]
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    spec = _parse_spec(name, raw, [path.parent])
    if spec.ocr_model:
        stack = select_ocr_stack(
            name=spec.ocr_model,
            language=spec.language,
            era=spec.era,
            script=spec.script,
            typeface=spec.typeface,
        )
        if stack:
            spec = replace(
                spec,
                tesseract_lang=stack.tesseract_lang or spec.tesseract_lang,
                tesseract_psm=stack.psm or spec.tesseract_psm,
                preprocess={**stack.preprocess, **spec.preprocess},
                ocr_model=stack.name,
            )
    return spec


def list_print_doc_types(*, extra_dirs: list[Path] | None = None) -> list[str]:
    names: set[str] = set()
    for d in (extra_dirs or []) + _builtin_dirs():
        if not d.is_dir():
            continue
        for p in d.glob("*.yaml"):
            names.add(p.stem)
    return sorted(names)


def suggest_print_doc_type(
    *,
    year: int | None = None,
    language: str | None = None,
    era: str | None = None,
    fingerprint_era: str | None = None,
    manifest: JobManifest | None = None,
) -> str:
    """Pick a print doc_type: orthogonal language × publication year."""
    if year is None and manifest is not None:
        year = infer_publication_year(manifest)
    if language is None and manifest is not None:
        language = manifest.print_language
    lang = normalize_print_language(language)
    if year is not None or lang != "auto":
        return resolve_doc_type_for_language_year(lang if lang != "auto" else None, year)

    era_hint = (fingerprint_era or era or "").lower()
    if "fraktur" in era_hint or "blackletter" in era_hint:
        return "eebo_blackletter"
    if "twentieth" in era_hint or "1900" in era_hint:
        return "twentieth_century"
    if "contemporary" in era_hint or "2000" in era_hint:
        return "contemporary_print"
    if "nineteenth" in era_hint or "1800" in era_hint:
        return "nineteenth_century"
    if "1700" in era_hint or "enlightenment" in era_hint:
        return "enlightenment_antiqua"
    return resolve_doc_type_for_language_year(None, None)


def apply_print_doc_type(settings: Settings, spec: PrintDocumentTypeSpec) -> Settings:
    """Merge a print doc_type spec into runtime settings (CLI/env still override if set)."""
    clean_print = spec.normalization_mode != "diplomatic"
    clean_variants = spec.normalization_mode == "modern"
    updates: dict[str, Any] = {
        "tesseract_lang": spec.tesseract_lang,
        "clean_print": clean_print,
        "clean_apply_variants": clean_variants,
        "print_doc_type": spec.name,
        "ocr_combination": settings.ocr_combination or spec.ocr_combination,
        "normalization_mode": spec.normalization_mode,
    }
    return settings.model_copy(update=updates)
