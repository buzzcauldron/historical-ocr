"""Bundle computational-ready exports."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from historical_ocr.config import JobPaths
from historical_ocr.lib.page_xml import text_to_tei
from historical_ocr.lib.protocol_text import plain_text_from_yaml_dict
from historical_ocr.models.manifest import JobManifest


def _page_text(page, job: JobPaths) -> str:
    if page.transcription_txt:
        p = job.root / page.transcription_txt
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    if page.clean_text_path:
        p = job.root / page.clean_text_path
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    if page.ocr_text_path:
        p = job.root / page.ocr_text_path
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    if page.transcription_yaml:
        p = job.root / page.transcription_yaml
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return plain_text_from_yaml_dict(data)
    return ""


def _export_page_artifacts(
    page,
    job: JobPaths,
    *,
    txt_dir: Path,
    xml_dir: Path,
) -> tuple[str | None, str | None]:
    """Write export/txt and export/xml for one page; return relative paths."""
    text = _page_text(page, job)
    if not text:
        return None, None

    txt_out = txt_dir / f"{page.page_id}.txt"
    xml_out = xml_dir / f"{page.page_id}.xml"
    txt_out.write_text(text + "\n", encoding="utf-8")

    if page.tei_path:
        src_tei = job.root / page.tei_path
        if src_tei.is_file():
            shutil.copy2(src_tei, xml_out)
        else:
            text_to_tei(page.page_id, text, xml_out)
    else:
        text_to_tei(page.page_id, text, xml_out)

    return (
        str(txt_out.relative_to(job.root)),
        str(xml_out.relative_to(job.root)),
    )


def export_job(job: JobPaths, manifest: JobManifest) -> dict[str, str]:
    job.ensure()
    txt_dir = job.export / "txt"
    xml_dir = job.export / "xml"
    txt_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)

    corpus_txt = job.export / "corpus.txt"
    corpus_jsonl = job.export / "corpus.jsonl"

    txt_parts: list[str] = []
    jsonl_lines: list[str] = []

    for page in manifest.pages:
        if page.status != "ok":
            continue
        text = _page_text(page, job)
        if not text:
            continue

        export_txt, export_xml = _export_page_artifacts(
            page, job, txt_dir=txt_dir, xml_dir=xml_dir,
        )

        txt_parts.append(f"## {page.page_id}\n{text}\n")
        jsonl_lines.append(
            json.dumps(
                {
                    "page_id": page.page_id,
                    "route": page.route,
                    "text": text,
                    "export_txt": export_txt,
                    "export_xml": export_xml,
                    "transcription_yaml": page.transcription_yaml,
                    "tei_path": page.tei_path,
                    "ocr_text_path": page.ocr_text_path,
                    "clean_text_path": page.clean_text_path,
                },
                ensure_ascii=False,
            ),
        )

    corpus_txt.write_text("\n".join(txt_parts), encoding="utf-8")
    corpus_jsonl.write_text(
        "\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""),
        encoding="utf-8",
    )

    manifest.export = {
        "corpus_txt": str(corpus_txt.relative_to(job.root)),
        "corpus_jsonl": str(corpus_jsonl.relative_to(job.root)),
        "txt_dir": str(txt_dir.relative_to(job.root)),
        "xml_dir": str(xml_dir.relative_to(job.root)),
        "tei_dir": str((job.export / "tei").relative_to(job.root)),
    }
    job.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest.export
