from pathlib import Path

from historical_ocr.lib.protocol_text import plain_text_from_yaml_dict
from historical_ocr.lib.tei_minimal import yaml_to_tei


def test_plain_text_from_yaml():
    data = {
        "transcriptionOutput": {
            "segments": [{"text": "line one"}, {"text": "line two"}],
        },
    }
    assert plain_text_from_yaml_dict(data) == "line one\n\nline two"


def test_yaml_to_tei(tmp_path: Path):
    src = tmp_path / "page_transcription.yaml"
    src.write_text(
        "transcriptionOutput:\n  segments:\n    - position: body\n      text: 'hello'\n",
        encoding="utf-8",
    )
    dst = tmp_path / "page.xml"
    yaml_to_tei(src, dst)
    xml = dst.read_text(encoding="utf-8")
    assert "hello" in xml
    assert "TEI" in xml
