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
