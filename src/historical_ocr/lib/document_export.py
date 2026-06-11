"""Production deliverables: one clean TXT + one merged TEI per job."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from historical_ocr import __version__
from historical_ocr.lib.layout_export import TEI_NS, lines_to_clean_txt, text_to_layout_result
from historical_ocr.lib.layout_ocr import LayoutOcrResult, read_layout_json
from historical_ocr.models.manifest import JobManifest

_T = f"{{{TEI_NS}}}"
_XML = "{http://www.w3.org/XML/1998/namespace}id"
ET.register_namespace("", TEI_NS)


@dataclass(frozen=True)
class PageSlice:
    page_id: str
    text: str
    image_name: str
    layout: LayoutOcrResult | None = None


def merge_document_txt(slices: list[PageSlice]) -> str:
    """Single reading edition: pages separated by a blank line, no markup."""
    parts = [s.text.strip() for s in slices if s.text.strip()]
    return "\n\n".join(parts) + ("\n" if parts else "")


def _tei_header(manifest: JobManifest, *, title: str) -> ET.Element:
    header = ET.Element(f"{_T}teiHeader")
    fd = ET.SubElement(header, f"{_T}fileDesc")
    ti = ET.SubElement(fd, f"{_T}titleStmt")
    title_el = ET.SubElement(ti, f"{_T}title")
    title_el.text = title

    pub = ET.SubElement(fd, f"{_T}publicationStmt")
    dist = ET.SubElement(pub, f"{_T}distributor")
    dist.text = "historical-ocr"
    date_el = ET.SubElement(pub, f"{_T}date")
    date_el.set("when", datetime.now(timezone.utc).date().isoformat())

    src_desc = ET.SubElement(fd, f"{_T}sourceDesc")
    for rec in manifest.sources:
        bibl = ET.SubElement(src_desc, f"{_T}bibl")
        bibl.set("type", rec.kind)
        bibl.text = rec.value

    enc = ET.SubElement(header, f"{_T}encodingDesc")
    editorial = ET.SubElement(enc, f"{_T}editorialDecl")
    norm = ET.SubElement(editorial, f"{_T}normalization")
    norm.set("method", manifest.normalization_mode or "diplomatic")
    note = ET.SubElement(norm, f"{_T}p")
    note.text = (
        f"Processed with historical-ocr {__version__}; "
        f"material={manifest.resolved_material or manifest.material_mode}; "
        f"print_doc_type={manifest.print_doc_type or '—'}; "
        f"print_language={manifest.print_language or 'auto'}; "
        f"year={manifest.publication_year or '—'}."
    )
    return header


def _append_page_div(parent: ET.Element, sl: PageSlice) -> None:
    from historical_ocr.lib.tei_layout import append_sectioned_page_content

    page_div = ET.SubElement(parent, f"{_T}div", type="page")
    page_div.set(_XML, sl.page_id)
    ET.SubElement(page_div, f"{_T}pb", n=sl.page_id)

    layout = sl.layout or text_to_layout_result(sl.text)
    append_sectioned_page_content(page_div, sl.page_id, layout)


def _append_facsimile(text_el: ET.Element, slices: list[PageSlice]) -> None:
    from historical_ocr.lib.tei_layout import append_sectioned_facsimile_zones

    fac = ET.SubElement(text_el, f"{_T}facsimile")
    for sl in slices:
        layout = sl.layout or text_to_layout_result(sl.text)
        surface = ET.SubElement(
            fac,
            f"{_T}surface",
            {
                _XML: f"surf_{sl.page_id}",
                "ulx": "0",
                "uly": "0",
                "lrx": str(layout.page_width),
                "lry": str(layout.page_height),
            },
        )
        if layout.sections:
            append_sectioned_facsimile_zones(surface, sl.page_id, layout)
        else:
            for line in layout.lines:
                if not line.text.strip():
                    continue
                ET.SubElement(
                    surface,
                    f"{_T}zone",
                    {
                        "rendition": "textline",
                        "ulx": str(line.left),
                        "uly": str(line.top),
                        "lrx": str(line.left + line.width),
                        "lry": str(line.top + line.height),
                        "corresp": f"#lb_{sl.page_id}_{line.line_num}",
                    },
                )


def write_document_tei(
    dst: Path,
    slices: list[PageSlice],
    manifest: JobManifest,
    *,
    title: str | None = None,
    include_facsimile: bool = True,
) -> None:
    root = ET.Element(f"{_T}TEI")
    root.append(_tei_header(manifest, title=title or manifest.job_id))
    text_el = ET.SubElement(root, f"{_T}text")
    body = ET.SubElement(text_el, f"{_T}body")
    for sl in slices:
        _append_page_div(body, sl)
    if include_facsimile and any(
        (sl.layout and sl.layout.lines) or sl.text.strip() for sl in slices
    ):
        _append_facsimile(text_el, slices)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def build_delivery_manifest(
    manifest: JobManifest,
    *,
    deliverables: dict[str, str],
    page_count: int,
) -> dict[str, Any]:
    return {
        "job_id": manifest.job_id,
        "export_basename": manifest.export_basename or manifest.job_id,
        "created_at": manifest.created_at,
        "software": f"historical-ocr {__version__}",
        "page_count": page_count,
        "resolved_material": manifest.resolved_material,
        "material_mode": manifest.material_mode,
        "print_doc_type": manifest.print_doc_type,
        "print_ocr_combination": manifest.print_ocr_combination,
        "normalization_mode": manifest.normalization_mode,
        "publication_year": manifest.publication_year,
        "print_language": manifest.print_language,
        "sources": [s.model_dump() for s in manifest.sources],
        "deliverables": deliverables,
        "routing_hints": [
            {"page_id": p.page_id, "hints": p.routing_hints}
            for p in manifest.pages
            if p.routing_hints
        ],
    }


def write_checksums(dst: Path, files: list[Path]) -> None:
    lines: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    dst.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def slice_from_page(
    page,
    job_root: Path,
    text: str,
    *,
    layout_path: Path | None = None,
) -> PageSlice:
    layout = read_layout_json(layout_path) if layout_path and layout_path.is_file() else None
    if layout is None and text.strip():
        layout = text_to_layout_result(text)
    image_name = Path(page.image_path).name
    clean = lines_to_clean_txt(layout.lines) if layout and layout.lines else text.strip()
    return PageSlice(page_id=page.page_id, text=clean, image_name=image_name, layout=layout)


def write_delivery_json(dst: Path, payload: dict[str, Any]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
