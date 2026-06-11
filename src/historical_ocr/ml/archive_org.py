"""Resolve Institutional Books barcodes to Internet Archive scans + page images."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable
import httpx

_USER_AGENT = (
    "historical-ocr/0.1 (+https://github.com/buzzcauldron/historical-ocr; research)"
)
_IA_SEARCH = "https://archive.org/advancedsearch.php"
_IIIF_MANIFEST = "https://iiif.archive.org/iiif/{ia_id}/manifest.json"


def _barcode_ia_candidates(barcode: str) -> list[str]:
    """Direct IA identifier guesses from an Institutional Books barcode."""
    b = (barcode or "").strip()
    if not b:
        return []
    out: list[str] = []
    if re.search(r"[a-zA-Z]", b):
        out.append(b)
    if b.startswith("hvd."):
        suffix = b[4:]
        if suffix and re.search(r"[a-zA-Z]", suffix):
            out.append(suffix)
    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def normalize_htid(barcode: str) -> str:
    b = (barcode or "").strip()
    if not b:
        return ""
    return b if b.startswith("hvd.") else f"hvd.{b}"


def _ia_search(query: str, *, rows: int = 5, client: httpx.Client) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "date"],
        "rows": rows,
        "output": "json",
    }
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            r = client.get(_IA_SEARCH, params=params)
            r.raise_for_status()
            data = r.json()
            docs = data.get("response", {}).get("docs", [])
            return docs if isinstance(docs, list) else []
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(min(60, 2 ** attempt))
    if last_exc is not None:
        raise last_exc
    return []


def ia_manifest_available(ia_id: str, *, client: httpx.Client) -> bool:
    url = _IIIF_MANIFEST.format(ia_id=ia_id)
    try:
        r = client.head(url, timeout=30.0)
        if r.status_code == 200:
            return True
        r = client.get(url, timeout=60.0)
        return r.status_code == 200 and bool(r.content)
    except httpx.HTTPError:
        return False


def build_archive_search_queries(record: dict[str, Any]) -> list[str]:
    """Ordered IA Solr queries for a metadata catalog row."""
    queries: list[str] = []
    barcode = str(record.get("barcode_src") or "").strip()
    if barcode and re.search(r"[a-zA-Z]", barcode):
        queries.append(f"identifier:{barcode}")

    htid = normalize_htid(barcode)
    if htid:
        queries.append(f"identifier:{htid}")
        queries.append(f"identifier:{htid.replace('.', '')}")

    ids = record.get("identifiers_src") or {}
    if isinstance(ids, dict):
        for oclc in ids.get("ocolc") or []:
            o = str(oclc).strip()
            if o:
                queries.append(f"oclc:{o}")
        for lccn in ids.get("lccn") or []:
            l = str(lccn).strip()
            if l:
                queries.append(f"lccn:{l}")

    title = str(record.get("title_src") or "").strip()
    year = record.get("publication_year_parsed")
    if title and year:
        safe = re.sub(r"\s+", " ", title)[:100].replace('"', "")
        queries.append(f'title:"{safe}" AND year:{int(year)} AND mediatype:texts')

    author = str(record.get("author_src") or "").strip()
    if title and author:
        safe_t = re.sub(r"\s+", " ", title)[:80].replace('"', "")
        safe_a = re.sub(r"\s+", " ", author)[:60].replace('"', "")
        queries.append(f'title:"{safe_t}" AND creator:"{safe_a}" AND mediatype:texts')

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def resolve_archive_identifier(
    record: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> str | None:
    """Return Internet Archive item identifier when IIIF scans exist."""
    own = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(connect=90.0, read=180.0, write=60.0, pool=60.0),
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )
    try:
        barcode = str(record.get("barcode_src") or "").strip()
        for candidate in _barcode_ia_candidates(barcode):
            if ia_manifest_available(candidate, client=http):
                return candidate

        for query in build_archive_search_queries(record):
            for doc in _ia_search(query, rows=5, client=http):
                ia_id = str(doc.get("identifier") or "").strip()
                if ia_id and ia_manifest_available(ia_id, client=http):
                    return ia_id
    finally:
        if own:
            http.close()
    return None


def page_image_urls_from_manifest(manifest: dict[str, Any]) -> list[str]:
    """Extract full-page JPEG URLs from an Internet Archive IIIF manifest."""
    urls: list[str] = []

    def _image_url(canvas: dict[str, Any]) -> str | None:
        for key in ("items",):
            for ann_page in canvas.get(key) or []:
                for ann in ann_page.get("items") or []:
                    body = ann.get("body") or {}
                    bid = body.get("id")
                    if isinstance(bid, str) and "/image/iiif/" in bid:
                        if "/full/" not in bid:
                            return f"{bid}/full/max/0/default.jpg"
                        return bid
        for img in canvas.get("images") or []:
            res = img.get("resource") or {}
            rid = res.get("@id") or res.get("id")
            if isinstance(rid, str):
                if "/full/" not in rid:
                    return f"{rid}/full/full/0/default.jpg"
                return rid
        return None

    if "sequences" in manifest:
        for canvas in (manifest.get("sequences") or [{}])[0].get("canvases") or []:
            u = _image_url(canvas)
            if u:
                urls.append(u)
    for canvas in manifest.get("items") or []:
        if str(canvas.get("type", "")).lower() == "canvas":
            u = _image_url(canvas)
            if u:
                urls.append(u)
    return urls


def fetch_archive_page_urls(
    ia_id: str,
    *,
    max_pages: int | None = None,
    client: httpx.Client | None = None,
) -> list[str]:
    own = client is None
    http = client or httpx.Client(
        timeout=120.0,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )
    try:
        r = http.get(_IIIF_MANIFEST.format(ia_id=ia_id))
        r.raise_for_status()
        manifest = r.json()
        urls = page_image_urls_from_manifest(manifest)
        if max_pages is not None:
            return urls[: max(0, max_pages)]
        return urls
    finally:
        if own:
            http.close()


def download_archive_pages(
    ia_id: str,
    out_dir: Path,
    *,
    max_pages: int = 40,
    client: httpx.Client | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[Path]:
    """Download up to *max_pages* JPEGs from an IA item."""
    out_dir.mkdir(parents=True, exist_ok=True)
    own = client is None
    http = client or httpx.Client(
        timeout=120.0,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    saved: list[Path] = []
    try:
        urls = fetch_archive_page_urls(ia_id, max_pages=max_pages, client=http)
        if not urls:
            return saved
        for i, url in enumerate(urls):
            dest = out_dir / f"page_{i + 1:04d}.jpg"
            if dest.is_file():
                saved.append(dest)
                continue
            for attempt in range(3):
                try:
                    r = http.get(url)
                    if r.status_code == 429:
                        time.sleep(min(30, 2 ** attempt))
                        continue
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                    saved.append(dest)
                    break
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        _log(f"ia skip page {i + 1}: {exc}")
                    else:
                        time.sleep(1 + attempt)
            time.sleep(0.25)
    finally:
        if own:
            http.close()
    return saved


def fetch_hf_volume_page_text(
    barcode: str,
    *,
    repo: str = "institutional/institutional-books-1.0",
    text_field: str = "text_by_page_gen",
    log_fn: Callable[[str], None] | None = None,
) -> list[str] | None:
    """Load per-page OCR text for one barcode from the full gated HF dataset."""
    try:
        from datasets import load_dataset
    except ImportError:
        return None

    target = normalize_htid(barcode)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    try:
        ds = load_dataset(repo, split="train", streaming=True)
    except Exception as exc:
        msg = str(exc).lower()
        if "gated" in msg or "authenticated" in msg or "401" in msg:
            _log("hf: not authenticated for page text — run: hf auth login (or export HF_TOKEN)")
            return None
        raise

    for row in ds:
        bc = str(row.get("barcode_src") or "")
        if normalize_htid(bc) != target and bc != barcode:
            continue
        pages = row.get(text_field) or row.get("text_by_page_src")
        if isinstance(pages, list) and pages:
            return [str(p) for p in pages]
        return None
    return None
