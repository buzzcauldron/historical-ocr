"""Bundle production exports (document.txt + document.xml) and internal artifacts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from historical_ocr.config import JobPaths, Settings
from historical_ocr.lib.glyph_heatmap import export_text_review
from historical_ocr.lib.document_export import (
    PageSlice,
    build_delivery_manifest,
    merge_document_txt,
    slice_from_page,
    write_checksums,
    write_delivery_json,
    write_document_tei,
)
from historical_ocr.lib.export_names import production_paths, resolve_export_basename
from historical_ocr.lib.layout_export import (
    layout_from_clean_text,
    lines_to_pagexml,
    lines_to_tei,
    text_to_layout_result,
)
from historical_ocr.lib.layout_ocr import read_layout_json
from historical_ocr.lib.page_xml import text_to_tei
from historical_ocr.lib.protocol_text import plain_text_from_yaml_dict
from historical_ocr.models.manifest import JobManifest
from historical_ocr.pipeline.paths import page_layout_json


def _page_text(page, job: JobPaths) -> str:
    if page.clean_text_path:
        p = job.root / page.clean_text_path
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    if page.transcription_txt:
        p = job.root / page.transcription_txt
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
    layout = read_layout_json(page_layout_json(job.root, page.page_id))
    if layout is not None:
        from historical_ocr.lib.layout_export import layout_result_to_clean_txt

        return layout_result_to_clean_txt(layout)
    return ""


def _export_page_internal(
    page,
    job: JobPaths,
    *,
    txt_dir: Path,
    xml_dir: Path,
    tei_dir: Path,
) -> tuple[str | None, str | None, str | None]:
    """Write per-page artifacts under export/_internal/."""
    text = _page_text(page, job)
    if not text:
        return None, None, None

    txt_out = txt_dir / f"{page.page_id}.txt"
    xml_out = xml_dir / f"{page.page_id}.xml"
    tei_out = tei_dir / f"{page.page_id}.xml"
    txt_out.write_text(text + "\n", encoding="utf-8")

    layout_path = page_layout_json(job.root, page.page_id)
    layout = layout_from_clean_text(layout_path, text) if layout_path.is_file() else None
    if layout is None:
        layout = read_layout_json(layout_path)

    image_name = Path(page.image_path).name
    if layout is not None and layout.lines:
        lines_to_pagexml(page.page_id, image_name, layout, xml_out)
        lines_to_tei(page.page_id, layout, tei_out)
    elif page.pagexml_path and (job.root / page.pagexml_path).is_file():
        import shutil

        shutil.copy2(job.root / page.pagexml_path, xml_out)
        if page.tei_path and (job.root / page.tei_path).is_file():
            shutil.copy2(job.root / page.tei_path, tei_out)
        else:
            text_to_tei(page.page_id, text, tei_out)
    elif page.tei_path and (job.root / page.tei_path).is_file():
        import shutil

        shutil.copy2(job.root / page.tei_path, tei_out)
        text_to_tei(page.page_id, text, xml_out)
    else:
        fallback = text_to_layout_result(text)
        lines_to_pagexml(page.page_id, image_name, fallback, xml_out)
        lines_to_tei(page.page_id, fallback, tei_out)

    return (
        str(txt_out.relative_to(job.root)),
        str(xml_out.relative_to(job.root)),
        str(tei_out.relative_to(job.root)),
    )


def export_job(
    job: JobPaths,
    manifest: JobManifest,
    *,
    export_internal: bool = True,
    tei_facsimile: bool = True,
    settings: Settings | None = None,
    log_fn=None,
) -> dict[str, str]:
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    job.ensure()
    internal = job.export / "_internal"
    txt_dir = internal / "txt"
    xml_dir = internal / "xml"
    tei_dir = internal / "tei"
    if export_internal:
        for d in (txt_dir, xml_dir, tei_dir):
            d.mkdir(parents=True, exist_ok=True)

    basename = resolve_export_basename(manifest)
    manifest.export_basename = basename
    _log(f"export: building {basename}.*")
    paths = production_paths(job.export, basename)
    document_txt = paths["txt"]
    document_xml = paths["xml"]
    delivery_json = paths["delivery_json"]
    checksums_path = paths["checksums"]
    corpus_jsonl = paths["corpus_jsonl"]

    slices: list[PageSlice] = []
    jsonl_lines: list[str] = []

    for page in manifest.pages:
        if page.status != "ok":
            continue
        text = _page_text(page, job)
        if not text:
            continue

        layout_path = page_layout_json(job.root, page.page_id)
        slices.append(
            slice_from_page(
                page,
                job.root,
                text,
                layout_path=layout_path if layout_path.is_file() else None,
            ),
        )

        export_txt = export_xml = export_tei = None
        if export_internal:
            export_txt, export_xml, export_tei = _export_page_internal(
                page,
                job,
                txt_dir=txt_dir,
                xml_dir=xml_dir,
                tei_dir=tei_dir,
            )
            jsonl_lines.append(
                json.dumps(
                    {
                        "page_id": page.page_id,
                        "route": page.route,
                        "text": text,
                        "export_txt": export_txt,
                        "export_xml": export_xml,
                        "export_tei": export_tei,
                    },
                    ensure_ascii=False,
                ),
            )

    _log(f"export: merging {len(slices)} page(s) → {document_txt.name}")
    document_txt.write_text(merge_document_txt(slices), encoding="utf-8")
    _log(f"export: writing TEI → {document_xml.name}")
    write_document_tei(
        document_xml,
        slices,
        manifest,
        title=basename,
        include_facsimile=tei_facsimile,
    )

    figures_dir = internal / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for page in manifest.pages:
        if page.status != "ok" or not page.transcription_yaml:
            continue
        src_fig = (job.root / page.transcription_yaml).parent / "figures"
        if not src_fig.is_dir():
            continue
        page_fig = figures_dir / page.page_id
        page_fig.mkdir(parents=True, exist_ok=True)
        for png in src_fig.glob("*.png"):
            shutil.copy2(png, page_fig / png.name)

    deliverables = {
        "document_txt": str(document_txt.relative_to(job.root)),
        "document_xml": str(document_xml.relative_to(job.root)),
    }

    s = settings or Settings()
    if s.symbol_filter and not s.fast_mode:
        review_pages = [
            (p.page_id, Path(p.image_path).name)
            for p in manifest.pages
            if p.status == "ok"
        ]
        deliverables.update(
            export_text_review(
                job.root,
                job.pages,
                job.export,
                basename=basename,
                document_txt=document_txt,
                pages=review_pages,
                render_heatmap=s.symbol_glyph_heatmap,
                conf_threshold=float(s.review_conf_threshold),
            ),
        )

    write_delivery_json(
        delivery_json,
        build_delivery_manifest(manifest, deliverables=deliverables, page_count=len(slices)),
    )
    checksum_files = [document_txt, document_xml]
    for key in ("text_review_json", "text_review_heatmap"):
        if key in deliverables:
            checksum_files.append(job.root / deliverables[key])
    write_checksums(checksums_path, checksum_files)
    if export_internal:
        corpus_jsonl.write_text(
            "\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""),
            encoding="utf-8",
        )

    manifest.export = {
        **deliverables,
        "delivery_json": str(delivery_json.relative_to(job.root)),
        "checksums": str(checksums_path.relative_to(job.root)),
        "figures_dir": str(figures_dir.relative_to(job.root)),
        # Legacy aliases for scripts that expect these keys
        "corpus_txt": str(document_txt.relative_to(job.root)),
    }
    if export_internal:
        manifest.export.update(
            {
                "internal_txt_dir": str(txt_dir.relative_to(job.root)),
                "internal_xml_dir": str(xml_dir.relative_to(job.root)),
                "internal_tei_dir": str(tei_dir.relative_to(job.root)),
                "corpus_jsonl": str(corpus_jsonl.relative_to(job.root)),
                "txt_dir": str(txt_dir.relative_to(job.root)),
                "xml_dir": str(xml_dir.relative_to(job.root)),
                "tei_dir": str(tei_dir.relative_to(job.root)),
            },
        )
    job.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    _log(f"export: complete → {document_txt.relative_to(job.root)}")
    return manifest.export
