"""Persist GUI form selections to JSON under the user config directory."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_STATE_VERSION = 1


def gui_state_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "historical-ocr" / "gui_state.json"
    return Path.home() / ".config" / "historical-ocr" / "gui_state.json"


def load_gui_state() -> dict[str, Any]:
    path = gui_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    if int(data.get("version", 0)) != _STATE_VERSION:
        return {}
    return data


def save_gui_state(data: dict[str, Any]) -> None:
    path = gui_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**data, "version": _STATE_VERSION}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
