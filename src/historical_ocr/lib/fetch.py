"""Minimal URL → image/PDF fetch.

Extracted from transcription-shell ``strigil_fetch.py`` and strigil's IIIF
discovery patterns. Covers direct assets, IIIF manifests, and HTML ``<img>``
fallback — not the full strigil adapter matrix.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
_PDF_SUFFIX = ".pdf"
_USER_AGENT = (
    "historical-ocr/0.1 (+https://github.com/buzzcauldron/historical-ocr; research)"
)


def _is_direct_image(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    return any(path.endswith(s) for s in _IMAGE_SUFFIXES)


def _is_pdf(url: str) -> bool:
    return unquote(urlparse(url).path).lower().endswith(_PDF_SUFFIX)


class HttpFetcher:
    def __init__(self, *, timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_bytes(self, url: str) -> bytes:
        for attempt in range(3):
            r = self._client.get(url)
            if r.status_code == 429:
                time.sleep(min(30, 2 ** attempt))
                continue
            r.raise_for_status()
            return r.content
        r.raise_for_status()
        return b""

    def fetch_html(self, url: str) -> tuple[bytes, str]:
        data = self.fetch_bytes(url)
        charset = "utf-8"
        return data, charset


def _walk_iiif_ids(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("@id", "id") and isinstance(v, str) and (
                "/full/" in v or v.endswith((".jpg", ".jpeg", ".png", ".tif"))
            ):
                out.append(v)
            else:
                _walk_iiif_ids(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_iiif_ids(item, out)


def _iiif_urls_from_manifest(manifest_bytes: bytes, base_url: str) -> list[str]:
    try:
        data = json.loads(manifest_bytes.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []

    candidates: list[str] = []
    _walk_iiif_ids(data, candidates)

    # Presentation API: build image requests from image service @id
    service_ids: list[str] = []
    _walk_iiif_ids(data, service_ids)
    for sid in service_ids:
        if "/iiif/" in sid.lower() and "/full/" not in sid.lower():
            candidates.append(f"{sid.rstrip('/')}/full/full/0/default.jpg")

    # De-dupe preserving order
    seen: set[str] = set()
    urls: list[str] = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _find_manifest_url(soup: BeautifulSoup, page_url: str, html: str) -> str | None:
    for link in soup.find_all("link", rel=True):
        rel = " ".join(link.get("rel", [])).lower()
        if "iiif" in rel or link.get("type", "").lower().endswith("json"):
            href = link.get("href")
            if href:
                return urljoin(page_url, href)
    m = re.search(r'"(https?://[^"]+/manifest\.json)"', html)
    if m:
        return m.group(1)
    m = re.search(r'"(https?://[^"]+/iiif/[^"]+/manifest)"', html, re.I)
    if m:
        return m.group(1)
    return None


def _img_urls_from_html(soup: BeautifulSoup, page_url: str) -> list[str]:
    urls: list[str] = []
    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        if not src or src.startswith("data:"):
            continue
        full = urljoin(page_url, src)
        if _is_direct_image(full):
            urls.append(full)
    return urls


def discover_asset_urls(
    url: str,
    fetcher: HttpFetcher,
    *,
    limit: int | None = None,
) -> list[str]:
    if _is_direct_image(url) or _is_pdf(url):
        return [url]

    raw, _ = fetcher.fetch_html(url)
    html = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    manifest_url = _find_manifest_url(soup, url, html)
    if manifest_url:
        try:
            manifest = fetcher.fetch_bytes(manifest_url)
            urls = _iiif_urls_from_manifest(manifest, manifest_url)
            if urls:
                return urls[:limit] if limit else urls
        except Exception:
            pass

    urls = _img_urls_from_html(soup, url)
    return urls[:limit] if limit else urls


def fetch_assets_from_url(
    url: str,
    out_dir: Path,
    *,
    limit: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[Path]:
    """Download images or a PDF from *url* into *out_dir*."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = HttpFetcher()
    saved: list[Path] = []

    def _log(msg: str) -> None:
        if progress:
            progress(msg)

    try:
        asset_urls = discover_asset_urls(url, fetcher, limit=limit)
        if not asset_urls:
            raise RuntimeError(f"No assets discovered at {url}")

        _log(f"Found {len(asset_urls)} asset URL(s).")
        for i, asset_url in enumerate(asset_urls):
            try:
                _log(f"Downloading {i + 1}/{len(asset_urls)}")
                data = fetcher.fetch_bytes(asset_url)
                parsed = unquote(urlparse(asset_url).path).lower()
                if parsed.endswith(_PDF_SUFFIX):
                    ext = _PDF_SUFFIX
                else:
                    ext = next(
                        (s for s in _IMAGE_SUFFIXES if parsed.endswith(s)),
                        ".jpg",
                    )
                stem = Path(unquote(urlparse(asset_url).path)).stem[:80] or f"asset_{i:04d}"
                dest = out_dir / f"{i:04d}_{stem}{ext}"
                dest.write_bytes(data)
                saved.append(dest)
            except Exception as e:
                _log(f"  skip: {e}")
    finally:
        fetcher.close()

    return saved
