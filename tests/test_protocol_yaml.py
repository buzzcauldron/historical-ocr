"""Transcription YAML from layout."""

from __future__ import annotations

from pathlib import Path

import yaml

from historical_ocr.lib.layout_ocr import LayoutOcrResult, OcrLine
from historical_ocr.lib.protocol_yaml import write_transcription_yaml


def test_write_transcription_yaml(tmp_path: Path) -> None:
    layout = LayoutOcrResult(
        lines=[
            OcrLine(line_num=1, text="Hello", left=0, top=0, width=10, height=10, conf=90.0),
            OcrLine(line_num=2, text="World", left=0, top=12, width=10, height=10, conf=88.0),
        ],
        page_width=100,
        page_height=100,
        full_text="Hello\nWorld",
    )
    out = write_transcription_yaml(
        layout,
        tmp_path / "page_transcription.yaml",
        page_id="p1",
        image_name="p1.jpg",
    )
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "Hello" in data["transcriptionOutput"]["segments"][0]["text"]
