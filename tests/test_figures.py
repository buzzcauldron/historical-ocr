"""Embedded figure protocol markers ([fig:id])."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from historical_ocr.figures.base import FigureResult
from historical_ocr.figures.markers import insert_markers
from historical_ocr.lib.tei_minimal import yaml_to_tei

TEI_NS = "http://www.tei-c.org/ns/1.0"


def _sample_yaml() -> dict:
    return {
        "transcriptionOutput": {
            "metadata": {"sourcePageId": "test-page"},
            "segments": [
                {
                    "text": "First line\nSecond line",
                    "lineRange": [1, 2],
                    "position": "body",
                },
            ],
        },
    }


def test_insert_markers_adds_fig_section(tmp_path: Path) -> None:
    yaml_path = tmp_path / "page_transcription.yaml"
    yaml_path.write_text(yaml.safe_dump(_sample_yaml(), sort_keys=False), encoding="utf-8")
    fig = FigureResult(
        id="fig_01",
        bbox=(10, 200, 100, 300),
        label="Picture",
        confidence=0.9,
        crop_path=tmp_path / "figures" / "page_fig_01.png",
    )
    n_markers, n_figs = insert_markers(
        yaml_path=yaml_path,
        lines_xml_path=None,
        figures=[fig],
    )
    assert n_markers == 1
    assert n_figs == 1
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    root = data["transcriptionOutput"]
    assert "[fig:fig_01]" in root["segments"][0]["text"]
    assert root["figures"][0]["id"] == "fig_01"


def test_yaml_to_tei_emits_figure_element(tmp_path: Path) -> None:
    data = _sample_yaml()
    data["transcriptionOutput"]["segments"][0]["text"] = "Line one\n[fig:fig_01]\nLine two"
    data["transcriptionOutput"]["figures"] = [
        {
            "id": "fig_01",
            "label": "Picture",
            "crop_path": "figures/page_fig_01.png",
            "bbox_page_px": [10, 200, 100, 300],
            "detector_confidence": 0.9,
        },
    ]
    yaml_path = tmp_path / "page_transcription.yaml"
    tei_path = tmp_path / "page.xml"
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    yaml_to_tei(yaml_path, tei_path)
    root = ET.parse(tei_path).getroot()
    figs = root.findall(f".//{{{TEI_NS}}}figure")
    assert len(figs) == 1
    assert figs[0].get("{http://www.w3.org/XML/1998/namespace}id") == "fig_01"
    graphic = figs[0].find(f"{{{TEI_NS}}}graphic")
    assert graphic is not None
    assert graphic.get("url") == "figures/page_fig_01.png"
