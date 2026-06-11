"""Tesseract training registry and line-pair helpers."""

from __future__ import annotations

from historical_ocr.ml.tesseract_train import (
    extract_line_pairs_from_page,
    list_sources,
    load_registry,
)


def test_load_registry_has_hf_sources() -> None:
    reg = load_registry()
    assert "chronicling-america" in reg.get("huggingface", {})
    assert reg.get("training", {}).get("model_name") == "histnews"


def test_list_sources_includes_local_newspaper_gt() -> None:
    ids = {s.source_id for s in list_sources()}
    assert "chronicling-america" in ids
    assert "institutional-books" in ids
    assert "newspaper_gt" in ids


def test_extract_line_pairs_empty_reference() -> None:
    from PIL import Image

    im = Image.new("RGB", (40, 40), color="white")
    assert extract_line_pairs_from_page(im, "  \n  ") == []
