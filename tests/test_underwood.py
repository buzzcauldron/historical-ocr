from historical_ocr.backends.ocr_cleanup import available, clean_text


def test_underwood_available():
    assert available()


def test_underwood_clean_smoke():
    raw = "damned fouls for the king-\ndom"
    out = clean_text(raw, apply_corrections=True, rejoin_linebreaks=True)
    assert isinstance(out, str)
    assert len(out) > 0
