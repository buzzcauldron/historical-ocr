"""TrOCR backend and weak-line retry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from historical_ocr.config import Settings
from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.lib.trocr_retry import retry_weak_lines_with_trocr


def test_trocr_disabled_is_noop() -> None:
    layout = LayoutOcrResult(
        lines=[OcrLine(line_num=1, text="hi", left=0, top=0, width=10, height=10, conf=40.0)],
        page_width=100,
        page_height=100,
        full_text="hi",
    )
    s = Settings.model_construct(trocr_enabled=False)
    out = retry_weak_lines_with_trocr(layout, Path("/tmp/x.jpg"), settings=s)
    assert out.lines[0].text == "hi"


@patch("historical_ocr.backends.trocr.transcribe_pil", return_value="fixed")
@patch("historical_ocr.backends.trocr.available", return_value=True)
def test_trocr_replaces_weak_line(_avail, mock_transcribe, tmp_path: Path) -> None:
    from PIL import Image

    img = tmp_path / "page.jpg"
    Image.new("RGB", (200, 100), "white").save(img)

    layout = LayoutOcrResult(
        lines=[
            OcrLine(line_num=1, text="garb1e", left=10, top=10, width=80, height=20, conf=45.0),
            OcrLine(line_num=2, text="ok", left=10, top=40, width=80, height=20, conf=90.0),
        ],
        page_width=200,
        page_height=100,
        full_text="garb1e\nok",
    )
    s = Settings.model_construct(
        trocr_enabled=True,
        trocr_conf_threshold=60.0,
        trocr_max_lines=10,
        trocr_model="microsoft/trocr-base-printed",
        trocr_repair_conf=78.0,
    )
    out = retry_weak_lines_with_trocr(layout, img, settings=s)
    assert out.lines[0].text == "fixed"
    assert out.lines[0].conf == 78.0
    assert out.lines[1].text == "ok"
    mock_transcribe.assert_called_once()


def test_trocr_describe() -> None:
    from historical_ocr.backends import trocr as trocr_backend

    assert "TrOCR" in trocr_backend.describe()
