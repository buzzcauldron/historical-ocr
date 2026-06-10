"""Download and merge page-CNN training images from HF + OCRDatasets + local GT."""

from __future__ import annotations

import io
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Literal

MaterialLabel = Literal["print", "manuscript"]
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    label: MaterialLabel
    kind: Literal["huggingface", "ocrdatasets", "remote_gt", "local"]
    default_limit: int
    notes: str = ""


def registry_path() -> Path:
    return Path(resources.files("historical_ocr.ml") / "page_cnn_sources.yaml")


def load_registry() -> dict[str, Any]:
    import yaml

    with registry_path().open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_sources() -> list[SourceSpec]:
    reg = load_registry()
    rows: list[SourceSpec] = []
    for kind in ("huggingface", "ocrdatasets", "remote_gt"):
        block = reg.get(kind) or {}
        for source_id, raw in block.items():
            rows.append(
                SourceSpec(
                    source_id=source_id,
                    label=raw["label"],
                    kind=kind,  # type: ignore[arg-type]
                    default_limit=int(raw.get("default_limit", 0)),
                    notes=str(raw.get("notes", "")),
                ),
            )
    return rows


def _valid_image(path: Path) -> bool:
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        return False
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def _save_pil_image(im, dest: Path, *, max_edge: int = 2048) -> None:
    from PIL import Image

    if not isinstance(im, Image.Image):
        raise TypeError("expected PIL Image")
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="JPEG", quality=90)


def _extract_image_from_sample(sample: dict[str, Any], field: str):
    from PIL import Image

    val = sample.get(field)
    if val is None:
        return None
    if isinstance(val, Image.Image):
        return val
    if isinstance(val, dict):
        if "bytes" in val and val["bytes"]:
            return Image.open(io.BytesIO(val["bytes"]))
        if "path" in val and val["path"]:
            return Image.open(val["path"])
    if isinstance(val, (bytes, bytearray)):
        return Image.open(io.BytesIO(val))
    if isinstance(val, str) and Path(val).is_file():
        return Image.open(val)
    return None


def fetch_huggingface_source(
    source_id: str,
    out_root: Path,
    *,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    reg = load_registry()
    raw = (reg.get("huggingface") or {}).get(source_id)
    if not raw:
        raise ValueError(f"unknown huggingface source: {source_id}")

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("pip install -e '.[ml]' (needs datasets + huggingface_hub)") from exc

    label: MaterialLabel = raw["label"]
    cap = limit if limit is not None else int(raw.get("default_limit", 100))
    dest_dir = out_root / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out_root)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    kwargs: dict[str, Any] = {}
    if raw.get("streaming"):
        kwargs["streaming"] = True
    ds = load_dataset(raw["repo"], split=raw.get("split", "train"), **kwargs)
    field = raw.get("image_field", "image")
    prefix = f"{source_id}_"
    existing = {p.name for p in dest_dir.glob(f"{prefix}*")}
    n = 0
    for i, sample in enumerate(ds):
        if n >= cap:
            break
        name = f"{prefix}{i:06d}.jpg"
        if name in existing:
            n += 1
            continue
        im = _extract_image_from_sample(sample, field)
        if im is None:
            continue
        dest = dest_dir / name
        try:
            _save_pil_image(im, dest)
        except Exception:
            continue
        n += 1
        if n % 100 == 0:
            _log(f"{source_id}: {n}/{cap}")

    manifest["sources"][source_id] = {
        "kind": "huggingface",
        "label": label,
        "fetched": n,
        "limit": cap,
        "repo": raw["repo"],
        "at": _now_iso(),
    }
    _save_manifest(out_root, manifest)
    _log(f"{source_id}: saved {n} → {dest_dir}")
    return n


def harvest_glob_source(
    source_id: str,
    out_root: Path,
    search_roots: list[Path],
    *,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    reg = load_registry()
    raw = None
    kind = ""
    for section in ("ocrdatasets", "remote_gt"):
        if source_id in (reg.get(section) or {}):
            raw = reg[section][source_id]
            kind = section
            break
    if not raw:
        raise ValueError(f"unknown harvest source: {source_id}")

    label: MaterialLabel = raw["label"]
    cap = limit if limit is not None else int(raw.get("default_limit", 500))
    dest_dir = out_root / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out_root)
    prefix = f"{source_id}_"

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    seen_dest = {p.name for p in dest_dir.glob(f"{prefix}*")}
    n = 0
    for root in search_roots:
        if not root.is_dir():
            _log(f"skip missing root: {root}")
            continue
        for src in sorted(root.rglob("*")):
            if n >= cap:
                break
            if not _valid_image(src):
                continue
            name = f"{prefix}{n:06d}{src.suffix.lower()}"
            if name in seen_dest:
                n += 1
                continue
            dest = dest_dir / name
            shutil.copy2(src, dest)
            seen_dest.add(name)
            n += 1
        if n >= cap:
            break

    manifest["sources"][source_id] = {
        "kind": kind,
        "label": label,
        "fetched": n,
        "limit": cap,
        "roots": [str(p) for p in search_roots],
        "at": _now_iso(),
    }
    _save_manifest(out_root, manifest)
    _log(f"{source_id}: copied {n} → {dest_dir}")
    return n


def harvest_ocrdatasets(
    source_id: str,
    out_root: Path,
    ocrdatasets_root: Path,
    *,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    reg = load_registry()
    raw = (reg.get("ocrdatasets") or {}).get(source_id)
    if not raw:
        raise ValueError(f"unknown ocrdatasets source: {source_id}")
    ref = raw.get("ocrdatasets_ref", source_id)
    candidates = [
        ocrdatasets_root / ref,
        ocrdatasets_root / "data" / ref,
        ocrdatasets_root.parent / ref,
    ]
    roots = [p for p in candidates if p.is_dir()]
    if not roots:
        raise FileNotFoundError(
            f"OCRDatasets path for {ref} not found under {ocrdatasets_root}. "
            f"Clone https://github.com/xinke-wang/OCRDatasets and download the dataset.",
        )
    return harvest_glob_source(
        source_id,
        out_root,
        roots,
        limit=limit,
        log_fn=log_fn,
    )


def harvest_akdeniz_gt(
    source_id: str,
    out_root: Path,
    akdeniz_home: Path | None = None,
    *,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    import os

    home = akdeniz_home or Path(os.environ.get("AKDENIZ_HOME", Path.home()))
    reg = load_registry()
    raw = (reg.get("remote_gt") or {}).get(source_id)
    if not raw:
        raise ValueError(f"unknown remote_gt source: {source_id}")
    roots = [home / rel for rel in raw.get("relative_paths", [])]
    return harvest_glob_source(source_id, out_root, roots, limit=limit, log_fn=log_fn)


def harvest_local_dir(
    src: Path,
    out_root: Path,
    *,
    label: MaterialLabel,
    prefix: str | None = None,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    """Copy images from a flat or nested folder into out_root/<label>/."""
    if not src.is_dir():
        raise FileNotFoundError(src)
    cap = limit or 10_000
    dest_dir = out_root / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix or src.name.replace("/", "_")
    n = 0
    for path in sorted(src.rglob("*")):
        if n >= cap:
            break
        if not _valid_image(path):
            continue
        dest = dest_dir / f"local_{stem}_{n:06d}{path.suffix.lower()}"
        if dest.is_file():
            n += 1
            continue
        shutil.copy2(path, dest)
        n += 1
    if log_fn:
        log_fn(f"local:{stem}: copied {n} → {dest_dir}")
    return n


def fetch_sources(
    out_root: Path,
    *,
    hf_sources: list[str] | None = None,
    ocrdatasets_sources: list[str] | None = None,
    remote_gt_sources: list[str] | None = None,
    ocrdatasets_root: Path | None = None,
    akdeniz_home: Path | None = None,
    extra_dirs: list[tuple[Path, MaterialLabel]] | None = None,
    limit: int | None = None,
    all_hf: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Fetch configured sources; returns per-source image counts."""
    reg = load_registry()
    hf_block = reg.get("huggingface") or {}
    if all_hf:
        hf_list = list(hf_block.keys())
    elif hf_sources:
        hf_list = hf_sources
    else:
        hf_list = ["ocr-quality", "ocr-pdf-degraded"]

    counts: dict[str, int] = {}
    for sid in hf_list:
        per_limit = limit
        if per_limit is None:
            per_limit = int(hf_block[sid].get("default_limit", 100))
        counts[sid] = fetch_huggingface_source(
            sid,
            out_root,
            limit=per_limit,
            log_fn=log_fn,
        )

    ocr_block = reg.get("ocrdatasets") or {}
    for sid in ocrdatasets_sources or []:
        if not ocrdatasets_root:
            raise ValueError(f"--ocrdatasets-root required for {sid}")
        per_limit = limit or int(ocr_block[sid].get("default_limit", 500))
        counts[sid] = harvest_ocrdatasets(
            sid,
            out_root,
            ocrdatasets_root,
            limit=per_limit,
            log_fn=log_fn,
        )

    gt_block = reg.get("remote_gt") or {}
    for sid in remote_gt_sources or []:
        per_limit = limit or int(gt_block[sid].get("default_limit", 2000))
        counts[sid] = harvest_akdeniz_gt(
            sid,
            out_root,
            akdeniz_home,
            limit=per_limit,
            log_fn=log_fn,
        )

    for src, label in extra_dirs or []:
        key = f"local:{src.name}"
        counts[key] = harvest_local_dir(src, out_root, label=label, log_fn=log_fn)

    return counts


def count_labeled(out_root: Path) -> dict[str, int]:
    return {
        label: len(list((out_root / label).glob("*"))) if (out_root / label).is_dir() else 0
        for label in ("print", "manuscript")
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _manifest_path(out_root: Path) -> Path:
    return out_root / "manifest.json"


def _load_manifest(out_root: Path) -> dict[str, Any]:
    path = _manifest_path(out_root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "sources": {}}


def _save_manifest(out_root: Path, manifest: dict[str, Any]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    _manifest_path(out_root).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
