"""Metadata-only fetch + filtering for Institutional Books 1.0 (no page images on HF)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_METADATA_FIELDS = (
    "barcode_src",
    "title_src",
    "author_src",
    "date1_src",
    "date2_src",
    "date_types_src",
    "page_count_src",
    "token_count_o200k_base_gen",
    "language_src",
    "language_gen",
    "topic_or_subject_src",
    "topic_or_subject_gen",
    "topic_or_subject_score_gen",
    "genre_or_form_src",
    "ocr_score_src",
    "ocr_score_gen",
    "likely_duplicates_barcodes_gen",
    "identifiers_src",
)


@dataclass(frozen=True)
class InstitutionalBooksFilters:
    language_gen: str | None = "eng"
    min_ocr_score_src: float | None = 70.0
    min_ocr_score_gen: float | None = 70.0
    min_year: int | None = 1800
    max_year: int | None = 1920
    exclude_likely_duplicates: bool = True
    limit: int = 5000

    @classmethod
    def from_registry(cls, raw: dict[str, Any], *, limit: int | None = None) -> InstitutionalBooksFilters:
        filt = raw.get("filters") or {}
        cap = limit if limit is not None else int(raw.get("default_limit", 5000))
        return cls(
            language_gen=filt.get("language_gen", "eng"),
            min_ocr_score_src=filt.get("min_ocr_score_src"),
            min_ocr_score_gen=filt.get("min_ocr_score_gen"),
            min_year=filt.get("min_year"),
            max_year=filt.get("max_year"),
            exclude_likely_duplicates=bool(filt.get("exclude_likely_duplicates", True)),
            limit=cap,
        )


def parse_publication_year(date1: str | None) -> int | None:
    """Best-effort year from MARC-style date1_src (e.g. '1850', '18uu')."""
    if not date1:
        return None
    m = re.search(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", str(date1))
    if not m:
        return None
    year = int(m.group(1))
    return year if 1000 <= year <= 2100 else None


def _score_ok(value: Any, minimum: float | None) -> bool:
    if minimum is None:
        return True
    try:
        return float(value) >= float(minimum)
    except (TypeError, ValueError):
        return False


def _row_languages(row: dict[str, Any]) -> set[str]:
    langs: set[str] = set()
    for key in ("language_src", "language_gen"):
        val = str(row.get(key) or "").strip().lower()
        if val:
            langs.add(val)
    dist = row.get("language_distribution_gen") or {}
    if isinstance(dist, dict):
        for code in dist.get("language") or []:
            if code:
                langs.add(str(code).strip().lower())
    return langs


def passes_institutional_books_filters(row: dict[str, Any], filters: InstitutionalBooksFilters) -> bool:
    if filters.language_gen:
        want = filters.language_gen.lower()
        langs = _row_languages(row)
        if langs and want not in langs:
            return False

    if not _score_ok(row.get("ocr_score_src"), filters.min_ocr_score_src):
        return False
    if not _score_ok(row.get("ocr_score_gen"), filters.min_ocr_score_gen):
        return False

    year = parse_publication_year(row.get("date1_src"))
    if filters.min_year is not None and year is not None and year < filters.min_year:
        return False
    if filters.max_year is not None and year is not None and year > filters.max_year:
        return False

    if filters.exclude_likely_duplicates:
        dups = row.get("likely_duplicates_barcodes_gen")
        if isinstance(dups, list) and dups:
            return False

    return True


def slim_record(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _METADATA_FIELDS:
        if key in row and row[key] is not None:
            out[key] = row[key]
    out["publication_year_parsed"] = parse_publication_year(row.get("date1_src"))
    return out


def fetch_institutional_books_metadata(
    out_root: Path,
    *,
    source_id: str,
    registry_entry: dict[str, Any],
    filters: InstitutionalBooksFilters | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    """Stream HF metadata rows into manifest.json + records.jsonl (no images or OCR text)."""
    try:
        from datasets import load_dataset
        from huggingface_hub.errors import GatedRepoError
    except ImportError as exc:
        raise RuntimeError("pip install datasets huggingface_hub") from exc

    filt = filters or InstitutionalBooksFilters.from_registry(registry_entry)
    repo = str(registry_entry.get("repo_metadata") or registry_entry["repo"])
    out_root = out_root.expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    _log(
        f"{source_id}: metadata-only fetch from {repo} "
        f"(lang={filt.language_gen}, ocr≥{filt.min_ocr_score_src}/{filt.min_ocr_score_gen}, "
        f"years={filt.min_year}–{filt.max_year}, limit={filt.limit})",
    )
    _log(f"{source_id}: text fields omitted — not tesstrain-ready without scan access")

    try:
        ds = load_dataset(repo, split="train", streaming=True)
    except GatedRepoError as exc:
        raise RuntimeError(
            f"{repo} is gated. Accept IDI terms on Hugging Face, then authenticate:\n"
            "  hf auth login\n"
            "or set HF_TOKEN to a read token with dataset access.",
        ) from exc
    records: list[dict[str, Any]] = []
    scanned = 0
    for row in ds:
        scanned += 1
        if not passes_institutional_books_filters(row, filt):
            continue
        records.append(slim_record(row))
        if len(records) >= filt.limit:
            break
        if scanned % 10_000 == 0:
            _log(f"{source_id}: scanned {scanned:,}, kept {len(records):,}")

    records_path = out_root / "records.jsonl"
    with records_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    manifest = {
        "version": 1,
        "source_id": source_id,
        "repo": repo,
        "kind": "metadata_only",
        "tesstrain_ready": False,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "filters": {
            "language_gen": filt.language_gen,
            "min_ocr_score_src": filt.min_ocr_score_src,
            "min_ocr_score_gen": filt.min_ocr_score_gen,
            "min_year": filt.min_year,
            "max_year": filt.max_year,
            "exclude_likely_duplicates": filt.exclude_likely_duplicates,
            "limit": filt.limit,
        },
        "scanned": scanned,
        "kept": len(records),
        "records_path": str(records_path.relative_to(out_root)),
        "notes": (
            "Institutional Books 1.0 — metadata filter catalog. "
            "Pair page scans via: tess fetch --source institutional-books --archive-org"
        ),
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _log(f"{source_id}: kept {len(records)} / {scanned:,} scanned → {records_path}")
    return len(records)


def load_catalog_records(catalog_dir: Path) -> list[dict[str, Any]]:
    records_path = catalog_dir / "records.jsonl"
    if not records_path.is_file():
        raise FileNotFoundError(f"catalog missing: {records_path} — run tess fetch --source institutional-books first")
    rows: list[dict[str, Any]] = []
    for line in records_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def fetch_institutional_archive_corpus(
    corpus_root: Path,
    catalog_dir: Path,
    *,
    registry_entry: dict[str, Any],
    volume_limit: int = 10,
    max_pages_per_volume: int = 30,
    hf_text: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Resolve Internet Archive scans for catalog rows → tess pages/ layout."""
    import httpx

    from historical_ocr.ml.archive_org import (
        download_archive_pages,
        fetch_hf_volume_page_text,
        resolve_archive_identifier,
    )

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    corpus_root = corpus_root.expanduser().resolve()
    pages_dir = corpus_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    repo_full = str(registry_entry.get("repo_full") or "institutional/institutional-books-1.0")
    records = load_catalog_records(catalog_dir)[: max(0, volume_limit)]

    stats = {"volumes": 0, "pages": 0, "resolved": 0, "unresolved": 0}
    resolutions_path = catalog_dir / "archive_resolutions.jsonl"
    if resolutions_path.is_file():
        resolutions_path.unlink()

    with httpx.Client(
        timeout=httpx.Timeout(connect=90.0, read=180.0, write=60.0, pool=60.0),
        headers={"User-Agent": "historical-ocr/0.1"},
        follow_redirects=True,
    ) as client:
        with resolutions_path.open("a", encoding="utf-8") as res_fh:
            for rec in records:
                barcode = str(rec.get("barcode_src") or "")
                if not barcode:
                    continue
                stats["volumes"] += 1
                try:
                    ia_id = resolve_archive_identifier(rec, client=client)
                except httpx.HTTPError as exc:
                    stats["unresolved"] += 1
                    _log(f"ia: lookup failed for {barcode}: {exc}")
                    continue
                res_row = {
                    "barcode_src": barcode,
                    "archive_org_id": ia_id,
                    "htid": barcode if barcode.startswith("hvd.") else f"hvd.{barcode}",
                }
                res_fh.write(json.dumps(res_row, ensure_ascii=False) + "\n")

                if not ia_id:
                    stats["unresolved"] += 1
                    _log(f"ia: no match for {barcode} ({rec.get('title_src', '')[:50]})")
                    continue

                stats["resolved"] += 1
                _log(f"ia: {barcode} → {ia_id}")

                page_texts: list[str] | None = None
                if hf_text:
                    page_texts = fetch_hf_volume_page_text(
                        barcode,
                        repo=repo_full,
                        log_fn=_log,
                    )

                stem = barcode.replace(".", "_")
                vol_dir = pages_dir / stem
                images = download_archive_pages(
                    ia_id,
                    vol_dir,
                    max_pages=max_pages_per_volume,
                    client=client,
                    log_fn=_log,
                )
                if not images:
                    continue

                if page_texts:
                    joined = "\n\n".join(page_texts[: len(images)])
                else:
                    joined = "\n".join(f"[page {i + 1}]" for i in range(len(images)))

                text_path = pages_dir / f"{stem}.txt"
                text_path.write_text(joined.rstrip() + "\n", encoding="utf-8")
                cover = images[0]
                import shutil

                image_path = pages_dir / f"{stem}.jpg"
                if not image_path.is_file():
                    shutil.copy2(cover, image_path)

                langs = _row_languages(rec)
                ocr_lang = "lat" if "lat" in langs else str(rec.get("language_gen") or "eng")
                meta = {
                    "source_id": "institutional-books",
                    "barcode_src": barcode,
                    "archive_org_id": ia_id,
                    "archive_org_url": f"https://archive.org/details/{ia_id}",
                    "image": str(image_path.relative_to(corpus_root)),
                    "text": str(text_path.relative_to(corpus_root)),
                    "ia_pages": len(images),
                    "language": ocr_lang,
                }
                (pages_dir / f"{stem}.json").write_text(
                    json.dumps(meta, indent=2) + "\n",
                    encoding="utf-8",
                )
                stats["pages"] += len(images)

    _log(
        f"institutional-books/ia: {stats['resolved']}/{stats['volumes']} resolved, "
        f"{stats['pages']} page images in {pages_dir}",
    )
    return stats
