"""OCR stack registry for diachronic print (Tesseract traineddata bundles)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from historical_ocr.paths import ocr_models_registry_dir

_ENV_RE = re.compile(r"\$\{(\w+)\}")


def _default_registry_dir() -> Path:
    return ocr_models_registry_dir()


def _expand_env(val: str) -> str:
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), val)


@dataclass
class OcrStackSpec:
    name: str
    engine: str = "tesseract"
    tesseract_lang: str = "eng"
    psm: int = 6
    languages: list[str] = field(default_factory=list)
    eras: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    typefaces: list[str] = field(default_factory=list)
    preprocess: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


def _parse_stack(raw: dict[str, Any], source: Path) -> OcrStackSpec:
    name = str(raw.get("name", source.stem))
    return OcrStackSpec(
        name=name,
        engine=str(raw.get("engine", "tesseract")),
        tesseract_lang=str(raw.get("tesseract_lang", raw.get("lang", "eng"))),
        psm=int(raw.get("psm", 6)),
        languages=list(raw.get("languages") or []),
        eras=list(raw.get("eras") or []),
        scripts=list(raw.get("scripts") or []),
        typefaces=list(raw.get("typefaces") or []),
        preprocess=dict(raw.get("preprocess") or {}),
        notes=str(raw.get("notes", "")),
    )


def load_all(registry_dir: Path | None = None) -> list[OcrStackSpec]:
    root = registry_dir or _default_registry_dir()
    if not root.is_dir():
        return []
    stacks: list[OcrStackSpec] = []
    for path in sorted(root.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        stacks.append(_parse_stack(raw, path))
    return stacks


def by_name(name: str, registry_dir: Path | None = None) -> OcrStackSpec | None:
    for spec in load_all(registry_dir):
        if spec.name == name:
            return spec
    return None


def _score(
    spec: OcrStackSpec,
    *,
    language: str,
    era: str,
    script: str,
    typeface: str,
) -> int:
    score = 0
    if language:
        lang = language.lower().split("-")[0]
        if any(lang in x.lower() or language.lower() in x.lower() for x in spec.languages):
            score += 4
    if era and any(era.lower() in x.lower() for x in spec.eras):
        score += 3
    if script and any(script.lower() in x.lower() for x in spec.scripts):
        score += 2
    if typeface and any(typeface.lower() in x.lower() for x in spec.typefaces):
        score += 2
    return score


def select_ocr_stack(
    *,
    name: str | None = None,
    language: str = "",
    era: str = "",
    script: str = "",
    typeface: str = "",
    registry_dir: Path | None = None,
) -> OcrStackSpec | None:
    if name:
        hit = by_name(name, registry_dir)
        if hit:
            return hit
    stacks = load_all(registry_dir)
    if not stacks:
        return None
    ranked = sorted(
        stacks,
        key=lambda s: _score(s, language=language, era=era, script=script, typeface=typeface),
        reverse=True,
    )
    best = ranked[0]
    if _score(best, language=language, era=era, script=script, typeface=typeface) == 0:
        return best
    return best
