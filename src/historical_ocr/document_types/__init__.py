"""Diachronic print document-type specifications (YAML)."""

from historical_ocr.document_types.era_chronology import ERA_BANDS, infer_publication_year
from historical_ocr.document_types.language_matrix import (
    LANGUAGE_ERA_MATRIX,
    resolve_doc_type_for_language_year,
)
from historical_ocr.document_types.language_overlay import apply_language_overlay
from historical_ocr.document_types.languages import (
    list_print_languages,
    normalize_print_language,
)
from historical_ocr.document_types.print_types import (
    PrintDocumentTypeSpec,
    apply_print_doc_type,
    list_print_doc_types,
    load_print_doc_type,
    suggest_print_doc_type,
)

__all__ = [
    "ERA_BANDS",
    "LANGUAGE_ERA_MATRIX",
    "PrintDocumentTypeSpec",
    "apply_language_overlay",
    "apply_print_doc_type",
    "infer_publication_year",
    "list_print_doc_types",
    "list_print_languages",
    "load_print_doc_type",
    "normalize_print_language",
    "resolve_doc_type_for_language_year",
    "suggest_print_doc_type",
]
