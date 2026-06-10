"""Language × era routing matrix (orthogonal to chronology)."""

from __future__ import annotations

from historical_ocr.document_types.era_chronology import ERA_BANDS, EraBand
from historical_ocr.document_types.languages import (
    AUTO_LANGUAGE,
    default_doc_type_for_language,
    normalize_print_language,
)

# Per-language era → doc_type bands. English uses the canonical ERA_BANDS.
LANGUAGE_ERA_MATRIX: dict[str, tuple[EraBand, ...]] = {
    "en": ERA_BANDS,
    "la": (
        EraBand(1475, 1700, "humanist_roman"),
        EraBand(1701, 1800, "humanist_roman"),
        EraBand(1801, 1900, "nineteenth_century"),
        EraBand(1901, 2000, "twentieth_century"),
        EraBand(2001, 2100, "contemporary_print"),
    ),
    "de": (
        EraBand(1475, 1599, "eebo_blackletter"),
        EraBand(1600, 1899, "german_fraktur"),
        EraBand(1900, 2000, "twentieth_century"),
        EraBand(2001, 2100, "contemporary_print"),
    ),
    "fr": (
        EraBand(1500, 1700, "early_modern_english"),
        EraBand(1701, 1900, "enlightenment_antiqua"),
        EraBand(1901, 2000, "twentieth_century"),
        EraBand(2001, 2100, "contemporary_print"),
    ),
    "it": (
        EraBand(1500, 1700, "humanist_roman"),
        EraBand(1701, 1900, "enlightenment_antiqua"),
        EraBand(1901, 2000, "twentieth_century"),
        EraBand(2001, 2100, "contemporary_print"),
    ),
    "es": (
        EraBand(1500, 1700, "early_modern_english"),
        EraBand(1701, 1900, "enlightenment_antiqua"),
        EraBand(1901, 2000, "twentieth_century"),
        EraBand(2001, 2100, "contemporary_print"),
    ),
}


def resolve_doc_type_for_language_year(
    language: str | None,
    year: int | None,
) -> str:
    """Combine orthogonal language + year into a print doc_type name."""
    lang = normalize_print_language(language)
    if lang == AUTO_LANGUAGE:
        lang = "en"
    bands = LANGUAGE_ERA_MATRIX.get(lang, ERA_BANDS)
    if year is None:
        return default_doc_type_for_language(lang)
    if year < bands[0].start:
        return bands[0].name
    for band in bands:
        if band.start <= year <= band.end:
            return band.name
    return bands[-1].name
