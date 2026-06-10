"""Canonical print languages (orthogonal to era/year)."""

from __future__ import annotations

from dataclasses import dataclass

AUTO_LANGUAGE = "auto"


@dataclass(frozen=True)
class PrintLanguage:
    code: str
    label: str
    tesseract_hint: str


PRINT_LANGUAGES: tuple[PrintLanguage, ...] = (
    PrintLanguage("auto", "Auto", ""),
    PrintLanguage("en", "English", "eng"),
    PrintLanguage("la", "Latin", "lat"),
    PrintLanguage("de", "German", "deu"),
    PrintLanguage("fr", "French", "fra"),
    PrintLanguage("it", "Italian", "ita"),
    PrintLanguage("es", "Spanish", "spa"),
)

_ALIASES: dict[str, str] = {
    "auto": "auto",
    "": "auto",
    "en": "en",
    "eng": "en",
    "en-latn": "en",
    "english": "en",
    "la": "la",
    "lat": "la",
    "la-latn": "la",
    "latin": "la",
    "de": "de",
    "deu": "de",
    "de-latn": "de",
    "german": "de",
    "fr": "fr",
    "fra": "fr",
    "fr-latn": "fr",
    "french": "fr",
    "it": "it",
    "ita": "it",
    "italian": "it",
    "es": "es",
    "spa": "es",
    "spanish": "es",
}

_DEFAULT_BY_LANGUAGE: dict[str, str] = {
    "en": "early_modern_english",
    "la": "humanist_roman",
    "de": "german_fraktur",
    "fr": "enlightenment_antiqua",
    "it": "humanist_roman",
    "es": "enlightenment_antiqua",
}


def list_print_languages() -> list[PrintLanguage]:
    return list(PRINT_LANGUAGES)


def normalize_print_language(value: str | None) -> str:
    if not value:
        return AUTO_LANGUAGE
    key = value.strip().lower().replace("_", "-")
    return _ALIASES.get(key, key if key in _DEFAULT_BY_LANGUAGE else "en")


def default_doc_type_for_language(language: str) -> str:
    lang = normalize_print_language(language)
    if lang == AUTO_LANGUAGE:
        return "early_modern_english"
    return _DEFAULT_BY_LANGUAGE.get(lang, "early_modern_english")
