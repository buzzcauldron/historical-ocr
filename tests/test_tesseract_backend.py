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
