"""Download newspaper page images + OCR ground truth from Chronicling America (HF)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from historical_ocr.lib.fetch import HttpFetcher

CHRONAM_REPO = "RevolutionCrossroads/loc_chronicling_america_1770-1810"
CHRONAM_SHARDS = [
    f"data/train-{i:05d}-of-00004.parquet" for i in range(4)
]
SplitName = Literal["train", "val"]


@dataclass(frozen=True)
class ChronamRecord:
    record_id: str
    lccn: str
    newspaper_title: str
    place_of_publication: str
    issue_date: str
    edition_order: str
    page: str
    web_url: str
    ocr_text: str
    ocr_url: str
    thumbnail_url: str
    jpeg2000_url: str
    pdf_url: str
    source_record_create_date: str | None

    @property
    def image_url(self) -> str:
        return iiif_full_from_thumbnail(self.thumbnail_url) or self.jpeg2000_url


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj)}")


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map parquet column names (mixed case) to stable snake_case keys."""
    out: dict[str, Any] = {}
    for key, val in row.items():
        nk = _norm_key(key)
        if nk == "web_url":
            nk = "web_url"
        if isinstance(val, datetime):
            val = val.date().isoformat() if nk.endswith("_date") else val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        out[nk] = val
    return out


def record_id_from_row(row: dict[str, Any]) -> str:
    norm = normalize_row(row)
    lccn = str(norm.get("lccn") or "unknown")
    issue = str(norm.get("issue_date") or "unknown")
    page = str(norm.get("page") or "0")
    edition = str(norm.get("edition_order") or "1")
    return f"{lccn}_{issue}_p{page}_e{edition}"


def assign_split(record_id: str, *, seed: int, val_ratio: float) -> SplitName:
    if val_ratio <= 0:
        return "train"
    if val_ratio >= 1:
        return "val"
    digest = hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return "val" if bucket < val_ratio else "train"


def iiif_full_from_thumbnail(url: str) -> str | None:
    """Upgrade a Chronicling America IIIF thumbnail URL to full-resolution JPEG."""
    if not url or "/full/" not in url:
        return None
    base = url.split("#", 1)[0]
    return re.sub(r"/full/[^/]+/[^/]+/[^/]+$", "/full/full/0/default.jpg", base)


def chronam_record_from_row(row: dict[str, Any]) -> ChronamRecord | None:
    norm = normalize_row(row)
    ocr_text = str(norm.get("ocr_text") or "").strip()
    if not ocr_text:
        return None
    thumb = str(norm.get("thumbnail_url") or "")
    jp2 = str(norm.get("jpeg2000_url") or "")
    if not thumb and not jp2:
        return None
    create = norm.get("source_record_create_date") or norm.get("source_record_creation_date")
    return ChronamRecord(
        record_id=record_id_from_row(norm),
        lccn=str(norm.get("lccn") or ""),
        newspaper_title=str(norm.get("newspaper_title") or ""),
        place_of_publication=str(norm.get("place_of_publication") or ""),
        issue_date=str(norm.get("issue_date") or ""),
        edition_order=str(norm.get("edition_order") or "1"),
        page=str(norm.get("page") or ""),
        web_url=str(norm.get("web_url") or ""),
        ocr_text=ocr_text,
        ocr_url=str(norm.get("ocr_url") or ""),
        thumbnail_url=thumb,
        jpeg2000_url=jp2,
        pdf_url=str(norm.get("pdf_url") or ""),
        source_record_create_date=str(create) if create else None,
    )


def iter_chronam_rows(
    *,
    repo: str = CHRONAM_REPO,
    shards: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    try:
        from huggingface_hub import hf_hub_download
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "pip install -e . (needs huggingface_hub + pyarrow)",
        ) from exc

    for shard in shards or CHRONAM_SHARDS:
        local = Path(shard)
        if local.is_file():
            path = str(local.resolve())
        else:
            path = hf_hub_download(repo, shard, repo_type="dataset")
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=64):
            cols = batch.schema.names
            for i in range(batch.num_rows):
                yield {name: batch.column(name)[i].as_py() for name in cols}


def _split_dirs(out_root: Path, split: SplitName) -> tuple[Path, Path, Path]:
    base = out_root / split
    return base / "images", base / "text", base / "meta"


def _manifest_path(out_root: Path) -> Path:
    return out_root / "manifest.json"


def load_manifest(out_root: Path) -> dict[str, Any]:
    path = _manifest_path(out_root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": 1,
        "source": CHRONAM_REPO,
        "records": {},
        "counts": {"train": 0, "val": 0},
    }


def save_manifest(out_root: Path, manifest: dict[str, Any]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    _manifest_path(out_root).write_text(
        json.dumps(manifest, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _save_image_from_url(
    fetcher: HttpFetcher,
    url: str,
    dest: Path,
    *,
    max_edge: int = 4096,
    attempts: int = 3,
) -> bool:
    from PIL import Image

    last_exc: Exception | None = None
    data = b""
    for attempt in range(attempts):
        try:
            data = fetcher.fetch_bytes(url)
            break
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                raise last_exc from None
    im = Image.open(io.BytesIO(data))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="JPEG", quality=92)
    return True


def fetch_newspaper_gt(
    out_root: Path,
    *,
    limit: int = 500,
    val_ratio: float = 0.1,
    seed: int = 42,
    skip_images: bool = False,
    shards: list[str] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Stream Chronicling America pages into train/val folders with OCR text GT."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not 0 <= val_ratio <= 1:
        raise ValueError("val_ratio must be between 0 and 1")

    out_root = out_root.expanduser().resolve()
    manifest = load_manifest(out_root)
    known: set[str] = set(manifest.get("records", {}))
    counts = {"train": 0, "val": 0}
    saved_total = 0
    fetcher = HttpFetcher(timeout=120.0)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    try:
        for row in iter_chronam_rows(shards=shards):
            if saved_total >= limit:
                break
            rec = chronam_record_from_row(row)
            if rec is None:
                continue
            if rec.record_id in known:
                split = manifest["records"][rec.record_id]["split"]
                counts[split] += 0  # already on disk
                continue

            split = assign_split(rec.record_id, seed=seed, val_ratio=val_ratio)
            img_dir, text_dir, meta_dir = _split_dirs(out_root, split)
            stem = rec.record_id.replace("/", "_")
            text_path = text_dir / f"{stem}.txt"
            meta_path = meta_dir / f"{stem}.json"
            image_path = img_dir / f"{stem}.jpg"

            text_dir.mkdir(parents=True, exist_ok=True)
            meta_dir.mkdir(parents=True, exist_ok=True)
            if not skip_images:
                img_dir.mkdir(parents=True, exist_ok=True)
            text_path.write_text(rec.ocr_text + "\n", encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "record_id": rec.record_id,
                        "split": split,
                        "lccn": rec.lccn,
                        "newspaper_title": rec.newspaper_title,
                        "place_of_publication": rec.place_of_publication,
                        "issue_date": rec.issue_date,
                        "edition_order": rec.edition_order,
                        "page": rec.page,
                        "web_url": rec.web_url,
                        "ocr_url": rec.ocr_url,
                        "thumbnail_url": rec.thumbnail_url,
                        "jpeg2000_url": rec.jpeg2000_url,
                        "pdf_url": rec.pdf_url,
                        "image_url": rec.image_url,
                        "source_record_create_date": rec.source_record_create_date,
                    },
                    indent=2,
                    default=_json_default,
                )
                + "\n",
                encoding="utf-8",
            )

            image_ok = False
            if not skip_images:
                try:
                    image_ok = _save_image_from_url(fetcher, rec.image_url, image_path)
                except Exception as exc:
                    _log(f"image skip {rec.record_id}: {exc}")
            else:
                image_ok = False

            manifest["records"][rec.record_id] = {
                "split": split,
                "stem": stem,
                "text": str(text_path.relative_to(out_root)),
                "meta": str(meta_path.relative_to(out_root)),
                "image": str(image_path.relative_to(out_root)) if image_ok else None,
            }
            known.add(rec.record_id)
            counts[split] += 1
            saved_total += 1

            if saved_total % 25 == 0:
                save_manifest(out_root, manifest)
                _log(f"saved {saved_total}/{limit} (train {counts['train']}, val {counts['val']})")

    finally:
        fetcher.close()

    manifest["counts"] = {
        "train": sum(1 for r in manifest["records"].values() if r["split"] == "train"),
        "val": sum(1 for r in manifest["records"].values() if r["split"] == "val"),
    }
    manifest["fetch"] = {
        "limit": limit,
        "val_ratio": val_ratio,
        "seed": seed,
        "skip_images": skip_images,
        "shards": shards or CHRONAM_SHARDS,
    }
    save_manifest(out_root, manifest)
    _log(
        f"done: {saved_total} new pages → {out_root} "
        f"(train {manifest['counts']['train']}, val {manifest['counts']['val']})",
    )
    return {
        "saved": saved_total,
        "train": counts["train"],
        "val": counts["val"],
        "total_train": manifest["counts"]["train"],
        "total_val": manifest["counts"]["val"],
    }
