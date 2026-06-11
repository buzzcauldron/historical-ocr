"""Historical font profiles and strange-letter detection."""

from __future__ import annotations

from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import load_print_doc_type
from historical_ocr.lib.glyph_classify import MarkKind, classify_token
from historical_ocr.lib.historical_fonts import (
    analyze_token_for_font,
    line_has_strange_letters,
    resolve_font_profile,
)
from historical_ocr.lib.symbol_filter import SymbolFilterOptions, needs_glyph_review, resolve_symbol_filter


def test_resolve_modern_roman_for_twentieth_century() -> None:
    spec = load_print_doc_type("twentieth_century")
    profile = resolve_font_profile(
        typeface=spec.typeface,
        script=spec.script,
        era=spec.era,
        language=spec.language,
    )
    assert profile.key == "modern_roman"


def test_resolve_fraktur_for_german_fraktur() -> None:
    spec = load_print_doc_type("german_fraktur")
    profile = resolve_font_profile(
        typeface=spec.typeface,
        script=spec.script,
        era=spec.era,
        language=spec.language,
    )
    assert profile.key == "fraktur"


def test_long_s_strange_on_modern_newsprint() -> None:
    profile = resolve_font_profile(era="twentieth_century", typeface="roman")
    finding = analyze_token_for_font("ſaid", profile, conf=85.0)
    assert finding is not None
    assert finding.anomalous is True
    assert "ſ" in finding.chars
    assert finding.keep is True


def test_long_s_ok_on_antiqua() -> None:
    profile = resolve_font_profile(era="enlightenment_antiqua", typeface="roman")
    assert analyze_token_for_font("ſaid", profile, conf=85.0) is None


def test_digit_in_word_flagged() -> None:
    profile = resolve_font_profile(era="twentieth_century")
    finding = analyze_token_for_font("l1ne", profile, conf=80.0)
    assert finding is not None
    assert "digit_in_word" in finding.reason


def test_classify_token_marks_strange_letter() -> None:
    profile = resolve_font_profile(era="twentieth_century")
    decision = classify_token(
        text="ſhop",
        conf=88.0,
        left=10,
        top=10,
        width=40,
        height=18,
        line_median_h=18.0,
        font_profile=profile,
    )
    assert decision.kind == MarkKind.STRANGE_LETTER
    assert decision.keep is True


def test_needs_glyph_review_for_font_anomaly() -> None:
    profile = resolve_font_profile(era="twentieth_century")
    opts = SymbolFilterOptions(enabled=True, glyph_filter=True, font_profile=profile)
    assert needs_glyph_review("ſhop", 90.0, opts) is True
    assert needs_glyph_review("shop", 90.0, opts) is False


def test_symbol_filter_resolves_font_from_doc_type() -> None:
    spec = load_print_doc_type("twentieth_century")
    opts = resolve_symbol_filter(Settings(), spec)
    assert opts.font_profile is not None
    assert opts.font_profile.key == "modern_roman"


def test_line_has_strange_letters() -> None:
    profile = resolve_font_profile(era="twentieth_century")
    assert line_has_strange_letters("normal prose here", profile, conf=90.0) is False
    assert line_has_strange_letters("a ſtrange word", profile, conf=90.0) is True
