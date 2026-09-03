"""Tesseract backend helpers."""

from __future__ import annotations

from historical_ocr.backends import tesseract as tess


def test_langs_in_bundle() -> None:
    assert tess.langs_in_bundle("lat+frk+eng") == {"lat", "frk", "eng"}


def test_missing_langs_subset() -> None:
    missing = tess.missing_langs("eng+lat", installed={"eng", "osd"})
    assert missing == ["lat"]


def test_describe_when_missing() -> None:
    text = tess.describe()
    assert "PATH" in text or "tesseract" in text.lower()


def test_resolve_lang_bundle_prepends_finetune() -> None:
    from pathlib import Path

    from historical_ocr.config import Settings

    s = Settings.model_construct(
        tesseract_finetune_lang="histnews",
        tesseract_finetune_path=Path("/tmp/does-not-exist.traineddata"),
    )
    assert tess.resolve_lang_bundle("lat+eng", s) == "lat+eng"

    s2 = Settings.model_construct(
        tesseract_finetune_lang="histnews",
        tesseract_finetune_path=Path(__file__),
    )
    assert tess.resolve_lang_bundle("eng", s2) == "histnews+eng"
    assert tess.resolve_lang_bundle("eng+lat", s2) == "histnews+eng+lat"
    # Agbeti-Messan et al. 2026: do not put an English LSTM first on Fraktur/Greek
    assert tess.resolve_lang_bundle("deu_latf+deu+lat", s2) == "deu_latf+deu+lat"
    assert tess.resolve_lang_bundle("lat+frk+eng", s2) == "lat+frk+eng"
    assert tess.resolve_lang_bundle("grc+eng", s2) == "grc+eng"
    assert tess.resolve_lang_bundle("ell+eng", s2) == "ell+eng"


def test_finetune_applies_to_antiqua_only() -> None:
    assert tess.finetune_applies_to("eng")
    assert tess.finetune_applies_to("fra+lat+eng")
    assert not tess.finetune_applies_to("frk+eng")
    assert not tess.finetune_applies_to("deu_latf+deu")
    assert not tess.finetune_applies_to("grc")
