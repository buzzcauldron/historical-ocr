"""Canonical artifact paths under a job directory."""

from __future__ import annotations

from pathlib import Path


def page_layout_json(job_root: Path, page_id: str) -> Path:
    return (job_root / "artifacts" / page_id / "layout.json").resolve()


def page_ink_layout_json(job_root: Path, page_id: str) -> Path:
    return (job_root / "artifacts" / page_id / "ink_layout.json").resolve()


def page_ink_layout_png(job_root: Path, page_id: str) -> Path:
    return (job_root / "artifacts" / page_id / "ink_layout.png").resolve()


def page_glyph_decisions_path(job_root: Path, page_id: str) -> Path:
    from historical_ocr.lib.glyph_heatmap import page_glyph_decisions_path as _path

    return _path(job_root, page_id).resolve()


def page_pagexml(job_root: Path, page_id: str) -> Path:
    return (job_root / "artifacts" / page_id / "page.xml").resolve()


def page_tei(job_root: Path, page_id: str) -> Path:
    return (job_root / "export" / "tei" / f"{page_id}.xml").resolve()


def lines_xml_path(artifacts_dir: Path, page_id: str) -> Path:
    return (artifacts_dir / page_id / "lines.xml").resolve()


def transcription_yaml_path(artifacts_dir: Path, page_id: str, image_path: Path) -> Path:
    return (artifacts_dir / page_id / f"{image_path.stem}_transcription.yaml").resolve()
