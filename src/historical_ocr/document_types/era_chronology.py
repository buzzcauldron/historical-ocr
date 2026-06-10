"""Publication-year → print doc_type routing (1500–present)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from historical_ocr.models.manifest import JobManifest

_YEAR_RE = re.compile(r"(?<![0-9])(1[5-9]\d{2}|20[0-3]\d)(?![0-9])")


@dataclass(frozen=True)
class EraBand:
    start: int
    end: int
    name: str


# English/Latin default chronology; language overrides applied in suggest_print_doc_type.
ERA_BANDS: tuple[EraBand, ...] = (
    EraBand(1475, 1499, "eebo_blackletter"),
    EraBand(1500, 1640, "early_modern_english"),
    EraBand(1641, 1700, "early_modern_english"),
    EraBand(1701, 1800, "enlightenment_antiqua"),
    EraBand(1801, 1900, "nineteenth_century"),
    EraBand(1901, 2000, "twentieth_century"),
    EraBand(2001, 2100, "contemporary_print"),
)


def suggest_for_year(year: int) -> str:
    if year < 1475:
        return "eebo_blackletter"
    for band in ERA_BANDS:
        if band.start <= year <= band.end:
            return band.name
    if year > 2100:
        return "contemporary_print"
    return "nineteenth_century"


def infer_publication_year(manifest: JobManifest) -> int | None:
    if manifest.publication_year is not None:
        y = int(manifest.publication_year)
        if 1400 <= y <= 2100:
            return y
    for src in manifest.sources:
        for match in _YEAR_RE.finditer(src.value):
            y = int(match.group(1))
            if 1500 <= y <= 2030:
                return y
    return None
