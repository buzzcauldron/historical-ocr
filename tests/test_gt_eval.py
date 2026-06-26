"""LLM-independent GT evaluation helpers."""

from __future__ import annotations

from historical_ocr.lib.rules_only import apply_rules_only_presets, rules_only_clean
from historical_ocr.config import Settings
from historical_ocr.ml.gt_eval import (
    character_error_rate,
    normalize_for_eval,
    word_error_rate,
)


def test_normalize_for_eval_collapses_whitespace() -> None:
    assert normalize_for_eval("  Hello\n\nWorld  ") == "hello world"


def test_character_error_rate_identical() -> None:
    cer, n = character_error_rate("The Delaware gazette", "The Delaware gazette")
    assert cer == 0.0
    assert n > 0


def test_character_error_rate_one_substitution() -> None:
    cer, _ = character_error_rate("abc", "abd")
    assert abs(cer - 1 / 3) < 1e-6


def test_word_error_rate_proxy() -> None:
    wer, n = word_error_rate("one two", "one three")
    assert n == 2
    assert wer > 0


def test_rules_only_presets_clear_llm() -> None:
    s = Settings.model_construct(clean_llm="gemini", clean_llm_model="gemini-2.5-flash")
    s = apply_rules_only_presets(s)
    assert s.clean_llm is None
    assert s.clean_print is True
    assert s.symbol_filter is True


def test_rules_only_clean_drops_orphan_line_without_llm() -> None:
    s = apply_rules_only_presets(Settings())
    raw = "Headline here\n1\nNext paragraph starts"
    out = rules_only_clean(raw, s)
    assert "1" not in out.splitlines()
    assert "Next paragraph" in out


def test_year_from_meta_parses_record_id() -> None:
    from historical_ocr.ml.gt_eval import _year_from_meta

    assert _year_from_meta({}, record_id="ca_sn82014385_1809-07-08_p1_e1") == 1809
    assert _year_from_meta({"source_record": "sn82014385_1810-05-30_p3_e1"}) == 1810
    assert _year_from_meta({"issue_date": "1797-06-14"}) == 1797
