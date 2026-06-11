"""Minimal transcription protocol YAML from layout OCR (for figure markers)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from historical_ocr.lib.layout_ocr import LayoutOcrResult


def layout_to_transcription_dict(
    layout: LayoutOcrResult,
    *,
    page_id: str,
    image_name: str,
) -> dict[str, Any]:
    line_texts = [ln.text for ln in layout.lines if ln.text.strip()]
    body = "\n".join(line_texts)
    return {
        "transcriptionOutput": {
            "metadata": {
                "sourcePageId": page_id,
                "imageFilename": image_name,
            },
            "segments": [
                {
                    "text": body,
                    "lineRange": [1, max(1, len(line_texts))],
                    "position": "body",
                },
            ],
        },
    }


def write_transcription_yaml(
    layout: LayoutOcrResult,
    path: Path,
    *,
    page_id: str,
    image_name: str,
) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = layout_to_transcription_dict(layout, page_id=page_id, image_name=image_name)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
