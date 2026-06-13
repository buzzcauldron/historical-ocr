"""Fetch HF OCR corpora and prepare tesstrain line-level ground truth."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from historical_ocr.ml.newspaper_gt import fetch_newspaper_gt

_DEFAULT_MODEL_NAME = "histnews"


@dataclass(frozen=True)
class TessSourceSpec:
    source_id: str
    kind: str
    start_model: str
    print_doc_type: str
    default_limit: int
    notes: str = ""


def registry_path() -> Path:
    return Path(resources.files("historical_ocr.ml") / "tesseract_train_sources.yaml")


def load_registry() -> dict[str, Any]:
    import yaml

    with registry_path().open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_sources() -> list[TessSourceSpec]:
    reg = load_registry()
    rows: list[TessSourceSpec] = []
    for section in ("huggingface", "local"):
        for sid, raw in (reg.get(section) or {}).items():
            rows.append(
                TessSourceSpec(
                    source_id=sid,
                    kind=str(raw.get("kind", section)),
                    start_model=str(raw.get("start_model", "eng")),
                    print_doc_type=str(raw.get("print_doc_type", "")),
                    default_limit=int(raw.get("default_limit", 1000)),
                    notes=str(raw.get("notes", "")),
                ),
            )
    return rows


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_line_pairs_from_page(
    image,
    reference_text: str,
    *,
    lang: str = "eng",
    min_line_chars: int = 3,
) -> list[tuple[Any, str]]:
    """Crop line images using Tesseract layout; GT text from reference lines (in order)."""
    from PIL import Image

    import pytesseract
    from pytesseract import Output

    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.convert("RGB")
    ref_lines = [ln.strip() for ln in reference_text.splitlines() if len(ln.strip()) >= min_line_chars]
    if not ref_lines:
        return []

    data = pytesseract.image_to_data(image, lang=lang, config="--psm 3", output_type=Output.DICT)
    n = len(data["text"])
    line_boxes: dict[tuple[int, int, int], list[tuple[int, int, int, int]]] = {}
    for i in range(n):
        txt = str(data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf >= 0 and conf < 30:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        left = int(data["left"][i])
        top = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        line_boxes.setdefault(key, []).append((left, top, left + w, top + h))

    boxes: list[tuple[int, int, int, int]] = []
    for key in sorted(line_boxes.keys()):
        parts = line_boxes[key]
        x0 = min(p[0] for p in parts)
        y0 = min(p[1] for p in parts)
        x1 = max(p[2] for p in parts)
        y1 = max(p[3] for p in parts)
        if x1 - x0 < 8 or y1 - y0 < 6:
            continue
        boxes.append((x0, y0, x1, y1))

    if not boxes:
        return []

    count = min(len(boxes), len(ref_lines))
    pairs: list[tuple[Any, str]] = []
    for i in range(count):
        x0, y0, x1, y1 = boxes[i]
        pad = 2
        crop = image.crop((
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(image.width, x1 + pad),
            min(image.height, y1 + pad),
        ))
        pairs.append((crop, ref_lines[i]))
    return pairs


def _manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def _load_manifest(root: Path) -> dict[str, Any]:
    path = _manifest_path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "sources": {}, "line_count": 0}


def _save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _manifest_path(root).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _write_line_pair(gt_dir: Path, stem: str, crop, text: str) -> None:
    from PIL import Image

    png = gt_dir / f"{stem}.png"
    txt = gt_dir / f"{stem}.gt.txt"
    if isinstance(crop, Image.Image):
        crop.save(png, format="PNG")
    else:
        shutil.copy2(crop, png)
    txt.write_text(text.rstrip() + "\n", encoding="utf-8")


def prepare_tesstrain_ground_truth(
    corpus_root: Path,
    out_root: Path,
    *,
    model_name: str | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Collect line PNG + .gt.txt pairs into tesstrain ground-truth directory."""
    reg = load_registry()
    train_cfg = reg.get("training") or {}
    model = model_name or str(train_cfg.get("model_name", _DEFAULT_MODEL_NAME))
    corpus_root = corpus_root.expanduser().resolve()
    out_root = out_root.expanduser().resolve()
    gt_dir = out_root / "tesstrain" / f"{model}-ground-truth"
    gt_dir.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    manifest = _load_manifest(corpus_root)
    line_idx = sum(1 for _ in gt_dir.glob("*.png"))
    pages_used = 0

    pages_dir = corpus_root / "pages"
    if pages_dir.is_dir():
        for meta_path in sorted(pages_dir.glob("*.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            image_path = corpus_root / str(meta.get("image", ""))
            text_path = corpus_root / str(meta.get("text", ""))
            if not image_path.is_file() or not text_path.is_file():
                continue
            ref = text_path.read_text(encoding="utf-8")
            from PIL import Image

            page_lang = str(meta.get("language") or "eng")
            with Image.open(image_path) as im:
                pairs = extract_line_pairs_from_page(im, ref, lang=page_lang)
            for crop, line_text in pairs:
                stem = f"{meta_path.stem}_{line_idx:07d}"
                _write_line_pair(gt_dir, stem, crop, line_text)
                line_idx += 1
            pages_used += 1

    stats = {
        "prepared_at": _now_iso(),
        "model_name": model,
        "ground_truth_dir": str(gt_dir),
        "line_pairs": line_idx,
        "pages_used": pages_used,
        "corpus_root": str(corpus_root),
        "start_model": str(train_cfg.get("start_model", "eng")),
        "max_iterations": int(train_cfg.get("max_iterations", 10000)),
    }
    manifest["tesstrain"] = stats
    _save_manifest(corpus_root, manifest)
    _log(f"tesstrain: {line_idx} line pairs → {gt_dir}")
    return stats


def fetch_hf_image_text_source(
    source_id: str,
    out_root: Path,
    *,
    limit: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    reg = load_registry()
    raw = (reg.get("huggingface") or {}).get(source_id)
    if not raw or raw.get("kind") != "hf_image_text":
        raise ValueError(f"unknown hf_image_text source: {source_id}")

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("pip install datasets huggingface_hub") from exc

    repo = str(raw["repo"])
    split = str(raw.get("split", "train"))
    cap = limit if limit is not None else int(raw.get("default_limit", 500))
    image_field = str(raw.get("image_field", "image"))
    text_field = str(raw.get("text_field", "text"))

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    pages_dir = out_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset(repo, split=split, streaming=True)
    n = 0
    for row in ds:
        if n >= cap:
            break
        text = str(row.get(text_field) or "").strip()
        image = row.get(image_field)
        if not text or image is None:
            continue
        from PIL import Image

        if not isinstance(image, Image.Image):
            continue
        stem = f"{source_id}_{n:06d}"
        image_path = pages_dir / f"{stem}.jpg"
        image.convert("RGB").save(image_path, format="JPEG", quality=90)
        text_path = pages_dir / f"{stem}.txt"
        text_path.write_text(text.rstrip() + "\n", encoding="utf-8")
        meta = {
            "source_id": source_id,
            "repo": repo,
            "image": str(image_path.relative_to(out_root)),
            "text": str(text_path.relative_to(out_root)),
        }
        (pages_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        n += 1
        if n % 50 == 0:
            _log(f"{source_id}: {n}/{cap}")
    _log(f"{source_id}: saved {n} pages")
    return n


def fetch_chronicling_to_tesseract_corpus(
    out_root: Path,
    *,
    limit: int = 2000,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    """Reuse newspaper_gt fetch into tess corpus layout."""
    tmp = out_root / "_ca_gt"
    stats = fetch_newspaper_gt(tmp, limit=limit, val_ratio=0.1, log_fn=log_fn)
    pages_dir = out_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    manifest_path = tmp / "manifest.json"
    if not manifest_path.is_file():
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rid, rec in sorted((manifest.get("records") or {}).items()):
        img = tmp / str(rec["image"])
        txt = tmp / str(rec["text"])
        if not img.is_file() or not txt.is_file():
            continue
        stem = f"ca_{rid}"
        dest_img = pages_dir / f"{stem}{img.suffix.lower()}"
        shutil.copy2(img, dest_img)
        dest_txt = pages_dir / f"{stem}.txt"
        shutil.copy2(txt, dest_txt)
        meta = {"source_id": "chronicling-america", "image": str(dest_img.relative_to(out_root)), "text": str(dest_txt.relative_to(out_root))}
        (pages_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        n += 1
    return n


def import_local_page_corpus(
    source_id: str,
    corpus_path: Path,
    out_root: Path,
    *,
    limit: int | None = None,
    split: str = "train",
    log_fn: Callable[[str], None] | None = None,
) -> int:
    from historical_ocr.ml.newspaper_gt import load_manifest

    corpus_path = corpus_path.expanduser().resolve()
    manifest = load_manifest(corpus_path)
    cap = limit or 10_000
    pages_dir = out_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for rid, rec in sorted((manifest.get("records") or {}).items()):
        if n >= cap:
            break
        if rec.get("split", "train") != split:
            continue
        img = corpus_path / str(rec["image"])
        text_rel = str(rec.get("text") or "")
        txt = corpus_path / str(text_rel)
        if not img.is_file() or not txt.is_file():
            continue
        stem = f"{source_id}_{rid}"
        dest_img = pages_dir / f"{stem}{img.suffix.lower()}"
        if not dest_img.is_file():
            shutil.copy2(img, dest_img)
        dest_txt = pages_dir / f"{stem}.txt"
        if not dest_txt.is_file():
            shutil.copy2(txt, dest_txt)
        meta = {"source_id": source_id, "image": str(dest_img.relative_to(out_root)), "text": str(dest_txt.relative_to(out_root))}
        (pages_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        n += 1
    if log_fn:
        log_fn(f"{source_id}: imported {n} pages from {corpus_path}")
    return n


def fetch_sources(
    out_root: Path,
    *,
    hf_sources: list[str] | None = None,
    local_sources: list[str] | None = None,
    limit: int | None = None,
    institutional_filters: dict[str, Any] | None = None,
    archive_org: bool = False,
    max_pages_per_volume: int = 30,
    hf_page_text: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, int]:
    reg = load_registry()
    hf_block = reg.get("huggingface") or {}
    if hf_sources is None:
        hf_sources = ["chronicling-america", "newspaper-ocr-gold", "ocr-quality"]

    counts: dict[str, int] = {}
    for sid in hf_sources:
        raw = hf_block.get(sid)
        if not raw:
            continue
        kind = raw.get("kind")
        per_limit = limit or int(raw.get("default_limit", 500))
        if kind == "chronicling_parquet":
            counts[sid] = fetch_chronicling_to_tesseract_corpus(out_root, limit=per_limit, log_fn=log_fn)
        elif kind == "hf_image_text":
            counts[sid] = fetch_hf_image_text_source(sid, out_root, limit=per_limit, log_fn=log_fn)
        elif kind == "metadata_only":
            from historical_ocr.ml.institutional_books import (
                InstitutionalBooksFilters,
                fetch_institutional_books_metadata,
            )

            filt = InstitutionalBooksFilters.from_registry(raw, limit=per_limit)
            if institutional_filters:
                filt = InstitutionalBooksFilters(
                    language_gen=institutional_filters.get("language_gen", filt.language_gen),
                    min_ocr_score_src=institutional_filters.get(
                        "min_ocr_score_src",
                        institutional_filters.get("min_ocr_score", filt.min_ocr_score_src),
                    ),
                    min_ocr_score_gen=institutional_filters.get(
                        "min_ocr_score_gen",
                        institutional_filters.get("min_ocr_score", filt.min_ocr_score_gen),
                    ),
                    min_year=institutional_filters.get("min_year", filt.min_year),
                    max_year=institutional_filters.get("max_year", filt.max_year),
                    exclude_likely_duplicates=institutional_filters.get(
                        "exclude_likely_duplicates",
                        filt.exclude_likely_duplicates,
                    ),
                    limit=per_limit,
                )
            dest = out_root / sid
            counts[sid] = fetch_institutional_books_metadata(
                dest,
                source_id=sid,
                registry_entry=raw,
                filters=filt,
                log_fn=log_fn,
            )
            if archive_org and counts[sid] > 0:
                from historical_ocr.ml.institutional_books import fetch_institutional_archive_corpus

                ia_stats = fetch_institutional_archive_corpus(
                    out_root,
                    dest,
                    registry_entry=raw,
                    volume_limit=per_limit,
                    max_pages_per_volume=max_pages_per_volume,
                    hf_text=hf_page_text,
                    log_fn=log_fn,
                )
                counts[f"{sid}-ia-pages"] = int(ia_stats.get("pages", 0))
        else:
            counts[sid] = 0

    local_block = reg.get("local") or {}
    for sid in local_sources or []:
        raw = local_block.get(sid)
        if not raw:
            continue
        path = Path(str(raw["path"]))
        counts[sid] = import_local_page_corpus(
            sid,
            path,
            out_root,
            limit=limit or int(raw.get("default_limit", 5000)),
            log_fn=log_fn,
        )
    return counts


def _resolve_tessdata_dir(
    tessdata: Path | None,
    *,
    start_model: str,
) -> Path | None:
    import os

    candidates: list[Path] = []
    if tessdata is not None:
        candidates.extend([tessdata.expanduser(), tessdata.expanduser() / "script"])
    for env_key in ("TESSDATA", "TESSDATA_PREFIX"):
        raw = os.environ.get(env_key)
        if raw:
            base = Path(raw).expanduser()
            candidates.extend([base, base / "script"])
    candidates.extend([
        Path("/opt/homebrew/share/tessdata/tessdata_best/script"),
        Path("/usr/local/share/tessdata/tessdata_best/script"),
        Path("/usr/share/tessdata/tessdata_best/script"),
    ])
    for cand in candidates:
        if cand.is_dir() and (cand / f"{start_model}.traineddata").is_file():
            return cand
    return tessdata.expanduser() if tessdata and tessdata.expanduser().is_dir() else None


def train_from_ground_truth_dir(
    ground_truth_dir: Path,
    out_model: Path,
    *,
    model_name: str,
    start_model: str = "eng",
    max_iterations: int = 10_000,
    ratio_train: float = 0.9,
    tesstrain_root: Path | None = None,
    tessdata_dir: Path | None = None,
    run_traineddata: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Fine-tune Tesseract from a flat directory of *.png + *.gt.txt line pairs."""
    import os
    import subprocess

    ground_truth_dir = ground_truth_dir.expanduser().resolve()
    out_model = out_model.expanduser().resolve()
    n_lines = len(list(ground_truth_dir.glob("*.png")))
    if n_lines < 100:
        return {
            "skipped": True,
            "reason": f"need at least 100 line pairs, have {n_lines}",
            "line_pairs": n_lines,
        }

    if tesstrain_root is None:
        tesstrain_root = ground_truth_dir.parent / "tesstrain_repo"
    tesstrain_root = tesstrain_root.expanduser().resolve()
    if not (tesstrain_root / "Makefile").is_file():
        raise FileNotFoundError(
            f"missing tesstrain at {tesstrain_root} — clone "
            "https://github.com/tesseract-ocr/tesstrain.git",
        )

    tessdata_resolved = _resolve_tessdata_dir(tessdata_dir, start_model=start_model)
    if tessdata_resolved is not None:
        eng_in_dir = tessdata_resolved / "eng.traineddata"
        eng_parent = tessdata_resolved.parent / "eng.traineddata"
        if not eng_in_dir.is_file() and eng_parent.is_file():
            eng_in_dir.symlink_to(eng_parent)
    env = dict(os.environ)
    if tessdata_resolved is not None:
        env["TESSDATA_PREFIX"] = str(tessdata_resolved)

    gt_link = tesstrain_root / "data" / f"{model_name}-ground-truth"
    gt_link.parent.mkdir(parents=True, exist_ok=True)
    if gt_link.exists() or gt_link.is_symlink():
        gt_link.unlink()
    gt_link.symlink_to(ground_truth_dir)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    make_targets = ["training"]
    if run_traineddata:
        make_targets.append("traineddata")

    for target in make_targets:
        cmd = [
            "make",
            "-C",
            str(tesstrain_root),
            target,
            f"MODEL_NAME={model_name}",
            f"START_MODEL={start_model}",
            f"MAX_ITERATIONS={max_iterations}",
            f"RATIO_TRAIN={ratio_train}",
            f"GROUND_TRUTH_DIR={ground_truth_dir}",
            "TESSDATA_REPO=_best",
        ]
        if tessdata_resolved is not None:
            cmd.append(f"TESSDATA={tessdata_resolved}")
        _log(f"train: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"tesstrain {target} failed: {(proc.stderr or proc.stdout)[-1200:]}")

    model_dir = tesstrain_root / "data" / model_name
    trained = model_dir / f"{model_name}.traineddata"
    if not trained.is_file():
        alt = sorted(model_dir.glob("*.traineddata"), key=lambda p: p.stat().st_mtime, reverse=True)
        trained = alt[0] if alt else trained
    if not trained.is_file():
        raise FileNotFoundError(f"no traineddata under {model_dir}")

    out_model.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(trained, out_model)
    meta = {
        "trained_at": _now_iso(),
        "model_name": model_name,
        "line_pairs": n_lines,
        "start_model": start_model,
        "max_iterations": max_iterations,
        "ratio_train": ratio_train,
        "ground_truth_dir": str(ground_truth_dir),
        "tesstrain_root": str(tesstrain_root),
        "path": str(out_model),
    }
    out_model.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    _log(f"saved {out_model}")
    return meta


def train_tesseract_model(
    data_root: Path,
    out_model: Path,
    *,
    model_name: str | None = None,
    max_iterations: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run tesstrain on the newspaper/HF corpus layout under *data_root*."""
    reg = load_registry()
    train_cfg = reg.get("training") or {}
    model = model_name or str(train_cfg.get("model_name", _DEFAULT_MODEL_NAME))
    data_root = data_root.expanduser().resolve()
    gt_dir = data_root / "tesstrain" / f"{model}-ground-truth"
    return train_from_ground_truth_dir(
        gt_dir,
        out_model,
        model_name=model,
        start_model=str(train_cfg.get("start_model", "eng")),
        max_iterations=max_iterations or int(train_cfg.get("max_iterations", 10000)),
        ratio_train=float(train_cfg.get("ratio_train", 0.9)),
        tesstrain_root=data_root / "tesstrain_repo",
        tessdata_dir=data_root / "tessdata_best",
        log_fn=log_fn,
    )
