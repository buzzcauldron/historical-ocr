"""Apply orthogonal language selection to a loaded print doc_type spec."""

from __future__ import annotations

from dataclasses import replace

from historical_ocr.document_types.languages import AUTO_LANGUAGE, normalize_print_language
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.ocr.model_registry import select_ocr_stack

_LANGUAGE_STACK: dict[str, str] = {
    "en": "eng_modern_historical",
    "la": "latin_humanist",
    "de": "deu_fraktur",
    "fr": "fra_early_modern",
    "it": "latin_humanist",
    "es": "spa_early_modern",
    "grc": "grc_polytonic",
    "el": "ell_modern",
}


def _stack_name_for(lang: str, spec: PrintDocumentTypeSpec) -> str | None:
    if lang == "el":
        # Historical Greek print is usually polytonic until post-1982 reform.
        era = (spec.era or "").lower()
        name = (spec.name or "").lower()
        if name == "greek_modern" or era in ("contemporary",):
            return "ell_modern"
        return "grc_polytonic"
    return _LANGUAGE_STACK.get(lang)


def apply_language_overlay(
    spec: PrintDocumentTypeSpec,
    language: str | None,
) -> PrintDocumentTypeSpec:
    """Swap Tesseract stack when user sets --print-language (explicit or auto doc_type)."""
    lang = normalize_print_language(language)
    if lang == AUTO_LANGUAGE:
        return spec

    stack_name = _stack_name_for(lang, spec)
    stack = select_ocr_stack(
        name=stack_name,
        language=lang,
        era=spec.era,
        script=spec.script,
        typeface=spec.typeface,
    )
    if stack is None:
        return spec
    return replace(
        spec,
        language=lang,
        tesseract_lang=stack.tesseract_lang,
        tesseract_psm=stack.psm or spec.tesseract_psm,
        preprocess={**stack.preprocess, **spec.preprocess},
        ocr_model=stack.name,
    )
