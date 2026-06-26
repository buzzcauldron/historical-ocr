"""Tesseract training registry and line-pair helpers."""

from __future__ import annotations

from historical_ocr.ml.tesseract_train import (
    _box_is_dummy,
    _resolve_tessdata_prefix,
    _write_spread_box,
    ensure_tesstrain_boxes,
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


def test_resolve_tessdata_prefix_finds_lstm_train_config() -> None:
    prefix = _resolve_tessdata_prefix(None)
    if prefix is not None:
        assert (prefix / "configs" / "lstm.train").is_file()


def test_spread_box_is_not_dummy(tmp_path) -> None:
    from PIL import Image

    png = tmp_path / "line.png"
    Image.new("RGB", (100, 20), "white").save(png)
    box = tmp_path / "line.box"
    _write_spread_box(png, "ab", box)
    assert not _box_is_dummy(box)
    lines = box.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].split()[1] != lines[1].split()[1]


def test_ensure_tesstrain_boxes_fixes_dummy_boxes(tmp_path) -> None:
    from PIL import Image

    png = tmp_path / "line.png"
    gt = tmp_path / "line.gt.txt"
    box = tmp_path / "line.box"
    Image.new("RGB", (120, 16), "white").save(png)
    gt.write_text("abc\n", encoding="utf-8")
    box.write_text("a 0 0 120 16 0\nb 0 0 120 16 0\nc 0 0 120 16 0\n", encoding="utf-8")
    assert _box_is_dummy(box)
    assert ensure_tesstrain_boxes(tmp_path) == 1
    assert not _box_is_dummy(box)
