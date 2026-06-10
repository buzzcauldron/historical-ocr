"""Plain text from Academic Transcription Protocol YAML.

Vendored from transcription-shell ``pipeline/run.py`` (_extract_plain_text).
"""

from __future__ import annotations

from typing import Any


def plain_text_from_yaml_dict(data: dict[str, Any]) -> str:
    root = data.get("transcriptionOutput", data)
    if not isinstance(root, dict):
        return ""
    segs = root.get("segments") or []
    texts = [
        seg["text"].strip()
        for seg in segs
        if isinstance(seg, dict) and isinstance(seg.get("text"), str) and seg["text"].strip()
    ]
    return "\n\n".join(texts)
