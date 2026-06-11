"""Symbol junk filtering for print OCR."""

from __future__ import annotations

from historical_ocr.backends import tesseract as tess_backend
from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine, apply_symbol_filter_to_result
from historical_ocr.lib.symbol_filter import (
    SymbolFilterOptions,
    is_orphan_damage_line,
    resolve_symbol_filter,
    sanitize_line,
    sanitize_ocr_text,
    should_drop_token,
)


def test_should_drop_low_confidence_symbol() -> None:
    opts = SymbolFilterOptions(enabled=True, min_confidence=60.0)
    assert should_drop_token("|", 30.0, opts) is True
    assert should_drop_token("...", 40.0, opts) is True
    assert should_drop_token("hello", 30.0, opts) is False


def test_should_drop_always_drop_chars() -> None:
    opts = SymbolFilterOptions(enabled=True)
    assert should_drop_token("|", 99.0, opts) is True
    assert should_drop_token("_", 95.0, opts) is True
    assert should_drop_token(":", 95.0, opts) is False


def test_sanitize_line_strips_trailing_rules() -> None:
    opts = SymbolFilterOptions(enabled=True)
    assert sanitize_line("demoralize|and|emasculate|", opts) == "demoralize|and|emasculate"
    assert sanitize_line("Black News |", opts) == "Black News"
    assert sanitize_line("| alone", opts) == "alone"
    assert sanitize_line("word|", opts) == "word"


def test_sanitize_ocr_text_multiline() -> None:
    opts = SymbolFilterOptions(enabled=True)
    raw = "line one |\n| junk\nkeep this"
    out = sanitize_ocr_text(raw, opts)
    assert "|" not in out.splitlines()[0]
    assert out.splitlines()[-1] == "keep this"


def test_apply_symbol_filter_to_layout_result() -> None:
    opts = SymbolFilterOptions(enabled=True)
    result = LayoutOcrResult(
        lines=[
            OcrLine(1, "Header |", 0, 0, 10, 10, 80.0),
            OcrLine(2, "Body text", 0, 20, 10, 10, 90.0),
        ],
        page_width=100,
        page_height=100,
        full_text="Header |\nBody text",
    )
    filtered = apply_symbol_filter_to_result(result, opts)
    assert filtered.lines[0].text == "Header"
    assert filtered.full_text == "Header\nBody text"


def test_resolve_symbol_filter_doc_type_override() -> None:
    settings = Settings(tesseract_char_blacklist="|")
    spec = PrintDocumentTypeSpec(name="x", tesseract_char_blacklist="|_`")
    opts = resolve_symbol_filter(settings, spec)
    assert opts.char_blacklist == "|_`"
    assert opts.always_drop_chars == frozenset("|_`")


def test_build_tesseract_config_blacklist() -> None:
    cfg = tess_backend.build_config(psm=3, char_blacklist="|_")
    assert "--psm 3" in cfg
    assert "tessedit_char_blacklist=|_" in cfg


def test_build_tesseract_config_whitelist_wins() -> None:
    cfg = tess_backend.build_config(psm=6, char_blacklist="|_", char_whitelist="abc")
    assert "tessedit_char_whitelist=abc" in cfg
    assert "blacklist" not in cfg


def test_resolve_glyph_heatmap_off_in_fast_mode() -> None:
    from historical_ocr.config import Settings
    from historical_ocr.lib.fast_presets import apply_fast_presets

    fast = apply_fast_presets(Settings())
    opts = resolve_symbol_filter(fast)
    assert opts.save_glyph_heatmap is False


def test_orphan_damage_line_drops_lone_digit() -> None:
    opts = SymbolFilterOptions(enabled=True)
    assert is_orphan_damage_line("1", opts) is True
    assert is_orphan_damage_line("l", opts) is True
    assert is_orphan_damage_line("word", opts) is False
    assert is_orphan_damage_line("1st", opts) is False


def test_sanitize_ocr_text_drops_orphan_lines() -> None:
    opts = SymbolFilterOptions(enabled=True)
    raw = "will see and build for a new day as bwana crawls to his grave. @\n1\n.At the level"
    out = sanitize_ocr_text(raw, opts)
    assert "1" not in out.splitlines()
    assert "At the level" in out


def test_symbol_filter_disabled_passthrough() -> None:
    opts = SymbolFilterOptions(enabled=False)
    assert sanitize_line("keep |", opts) == "keep |"
    assert should_drop_token("|", 10.0, opts) is False
