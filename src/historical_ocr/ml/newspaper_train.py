"""Prepare and train newspaper OCR models from GT corpora (CA + user corrections)."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from historical_ocr.ml.newspaper_gt import load_manifest as load_gt_manifest

DEFAULT_TRAIN_ROOT = Path("data/newspaper_ocr")
DEFAULT_TRAIN_STATE = Path("models/newspaper_ocr.state.json")
_KETOS_LINE_RE = re.compile(r"[\t\n\r]")
MIN_TRAIN_LINES = 10
MIN_VAL_PAGES = 1
PLATEAU_EPS = 1e-4
PLATEAU_PATIENCE = 2


@dataclass(frozen=True)
class CorpusSource:
    name: str
    path: Path
    prefix: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ketos_line(image: Path, text: str) -> str:
    """Kraken ketos format: ``<image-path> <transcription>`` (single line)."""
    flat = " ".join(text.split())
    flat = _KETOS_LINE_RE.sub(" ", flat).strip()
    return f"{image}\t{flat}"


def _iter_source_records(corpus: Path) -> list[tuple[str, dict[str, Any]]]:
    manifest = load_gt_manifest(corpus)
    return sorted((rid, rec) for rid, rec in (manifest.get("records") or {}).items())


def prepare_training_corpus(
    out_root: Path,
    *,
    sources: list[CorpusSource] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Merge newspaper_gt + user_gt (+ extras) into a unified train/val OCR corpus."""
    out_root = out_root.expanduser().resolve()
    if sources is None:
        sources = [
            CorpusSource("chronicling_america", Path("data/newspaper_gt"), "ca"),
            CorpusSource("user_corrections", Path("data/user_gt"), "user"),
        ]

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    manifest: dict[str, Any] = {
        "version": 1,
        "prepared_at": _now_iso(),
        "sources": [],
        "records": {},
        "counts": {"train": 0, "val": 0},
    }
    ketos_dir = out_root / "ketos"
    ketos_dir.mkdir(parents=True, exist_ok=True)
    train_lines: list[str] = []
    val_lines: list[str] = []

    for src in sources:
        corpus = src.path.expanduser().resolve()
        if not corpus_manifest_path(corpus).is_file():
            _log(f"skip missing corpus: {corpus}")
            continue
        n = 0
        for record_id, rec in _iter_source_records(corpus):
            split = str(rec.get("split") or "train")
            if split not in ("train", "val"):
                split = "train"
            stem = f"{src.prefix}_{record_id}"
            text_path = corpus / str(rec["text"])
            image_rel = rec.get("image")
            if not text_path.is_file() or not image_rel:
                continue
            image_src = corpus / str(image_rel)
            if not image_src.is_file():
                continue

            img_dir = out_root / split / "images"
            txt_dir = out_root / split / "text"
            meta_dir = out_root / split / "meta"
            for d in (img_dir, txt_dir, meta_dir):
                d.mkdir(parents=True, exist_ok=True)

            ext = image_src.suffix.lower() or ".jpg"
            image_dest = img_dir / f"{stem}{ext}"
            if image_src.resolve() != image_dest.resolve():
                shutil.copy2(image_src, image_dest)

            text = text_path.read_text(encoding="utf-8")
            (txt_dir / f"{stem}.txt").write_text(text.rstrip() + "\n", encoding="utf-8")

            source_meta: dict[str, Any] = {}
            source_meta_rel = rec.get("meta")
            if source_meta_rel:
                source_meta_path = corpus / str(source_meta_rel)
                if source_meta_path.is_file():
                    source_meta = json.loads(source_meta_path.read_text(encoding="utf-8"))

            meta = {
                "record_id": stem,
                "split": split,
                "source_corpus": src.name,
                "source_record": record_id,
            }
            for key in (
                "issue_date",
                "lccn",
                "newspaper_title",
                "place_of_publication",
                "page",
                "edition_order",
            ):
                if key in source_meta:
                    meta[key] = source_meta[key]
            if "issue_date" not in meta:
                m2 = re.search(r"_(\d{4}-\d{2}-\d{2})_", record_id)
                if m2:
                    meta["issue_date"] = m2.group(1)
            (meta_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

            line = _ketos_line(image_dest.resolve(), text)
            transcription = line.split("\t", 1)[-1].strip()
            if not transcription:
                _log(f"skip empty text: {stem}")
                continue

            if split == "val":
                val_lines.append(line)
            else:
                train_lines.append(line)

            manifest["records"][stem] = {
                "split": split,
                "stem": stem,
                "source": src.name,
                "image": str(image_dest.relative_to(out_root)),
                "text": str((txt_dir / f"{stem}.txt").relative_to(out_root)),
                "meta": str((meta_dir / f"{stem}.json").relative_to(out_root)),
            }
            n += 1
        manifest["sources"].append({"name": src.name, "path": str(corpus), "imported": n})
        _log(f"{src.name}: {n} pages")

    (ketos_dir / "train.txt").write_text("\n".join(train_lines) + ("\n" if train_lines else ""), encoding="utf-8")
    (ketos_dir / "val.txt").write_text("\n".join(val_lines) + ("\n" if val_lines else ""), encoding="utf-8")
    manifest["counts"] = {
        "train": len(train_lines),
        "val": len(val_lines),
    }
    manifest["ketos"] = {
        "train": str((ketos_dir / "train.txt").relative_to(out_root)),
        "val": str((ketos_dir / "val.txt").relative_to(out_root)),
    }
    save_train_manifest(out_root, manifest)
    _log(f"prepared {manifest['counts']['train']} train, {manifest['counts']['val']} val → {out_root}")
    return manifest


def corpus_manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def save_train_manifest(root: Path, manifest: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    corpus_manifest_path(root).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_train_manifest(root: Path) -> dict[str, Any]:
    path = corpus_manifest_path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "records": {}, "counts": {"train": 0, "val": 0}}


def train_state_path(data_root: Path) -> Path:
    return data_root / "train_state.json"


def load_train_state(data_root: Path) -> dict[str, Any]:
    path = train_state_path(data_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_train_state(data_root: Path, state: dict[str, Any]) -> Path:
    path = train_state_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def _count_train_lines(data_root: Path) -> int:
    train_file = data_root / "ketos" / "train.txt"
    if not train_file.is_file():
        return 0
    return sum(1 for ln in train_file.read_text(encoding="utf-8").splitlines() if ln.strip())


def train_newspaper_ocr(
    data_root: Path,
    out_model: Path,
    *,
    patience: int = PLATEAU_PATIENCE,
    eval_limit: int | None = None,
    user_corpus: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Tune rules from corrections, eval val CER, exit when metrics plateau (no Kraken)."""

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    from historical_ocr.ml.gt_eval import eval_newspaper_gt
    from historical_ocr.ml.user_corrections import DEFAULT_CORPUS, tune_corpus

    data_root = data_root.expanduser().resolve()
    out_state = out_model.expanduser().resolve()
    if not (data_root / "manifest.json").is_file():
        raise FileNotFoundError(
            f"missing {data_root / 'manifest.json'} — run: historical-ocr newspaper prepare",
        )

    manifest = load_train_manifest(data_root)
    n_train = int(manifest.get("counts", {}).get("train", 0)) or _count_train_lines(data_root)
    n_val = int(manifest.get("counts", {}).get("val", 0))
    if n_train < MIN_TRAIN_LINES:
        reason = f"need at least {MIN_TRAIN_LINES} training pages, have {n_train}"
        _log(f"skip: {reason}")
        return {
            "skipped": True,
            "reason": reason,
            "train_lines": n_train,
            "data_root": str(data_root),
            "state": str(out_state),
        }
    if n_val < MIN_VAL_PAGES:
        reason = f"need at least {MIN_VAL_PAGES} val pages for plateau eval, have {n_val}"
        _log(f"skip: {reason}")
        return {
            "skipped": True,
            "reason": reason,
            "val_pages": n_val,
            "data_root": str(data_root),
            "state": str(out_state),
        }

    corpus = (user_corpus or DEFAULT_CORPUS).expanduser().resolve()
    tune_stats: dict[str, Any] = {"rules": 0, "path": None}
    if corpus_manifest_path(corpus).is_file():
        _log(f"tune: mining rules from {corpus}")
        tune_stats = tune_corpus(corpus, log_fn=_log)
    else:
        _log(f"tune: skip — no user corpus at {corpus}")

    prev = load_train_state(data_root)
    prev_best = prev.get("best_mean_cer")
    plateau_rounds = int(prev.get("plateau_rounds", 0))

    _log(f"eval: val split ({n_val} pages)")
    report = eval_newspaper_gt(
        data_root,
        split="val",
        limit=eval_limit,
        log_fn=_log,
    )
    mean_cer = report.get("mean_cer")
    mean_wer = report.get("mean_wer")
    scored = int(report.get("scored") or 0)
    if not scored or mean_cer is None:
        reason = "val eval scored 0 pages"
        _log(f"skip: {reason}")
        return {
            "skipped": True,
            "reason": reason,
            "data_root": str(data_root),
            "state": str(out_state),
        }

    improved = prev_best is None or float(mean_cer) < float(prev_best) - PLATEAU_EPS
    if improved:
        plateau_rounds = 0
        best_mean_cer = float(mean_cer)
        _log(f"improved: mean CER {mean_cer:.4f}" + (f" (was {prev_best:.4f})" if prev_best is not None else ""))
    else:
        plateau_rounds += 1
        best_mean_cer = float(prev_best) if prev_best is not None else float(mean_cer)
        _log(
            f"flat: mean CER {mean_cer:.4f} "
            f"(best {best_mean_cer:.4f}, plateau {plateau_rounds}/{patience})",
        )

    state = {
        "version": 1,
        "trained_at": _now_iso(),
        "backend": "tune_rules",
        "data_root": str(data_root),
        "train_pages": n_train,
        "val_pages": n_val,
        "mean_cer": float(mean_cer),
        "mean_wer": float(mean_wer) if mean_wer is not None else None,
        "best_mean_cer": best_mean_cer,
        "plateau_rounds": plateau_rounds,
        "plateau_patience": patience,
        "rule_count": tune_stats.get("rules", 0),
        "rules_path": tune_stats.get("path"),
        "eval_report": report.get("at"),
    }
    save_train_state(data_root, state)
    out_state.parent.mkdir(parents=True, exist_ok=True)
    out_state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    _log(f"state → {out_state}")

    if not improved and plateau_rounds >= patience:
        return {
            "skipped": True,
            "reason": f"plateau: mean CER flat for {plateau_rounds} rounds",
            "mean_cer": float(mean_cer),
            "best_mean_cer": best_mean_cer,
            "plateau_rounds": plateau_rounds,
            "state": str(out_state),
        }

    return {
        "trained": True,
        "improved": improved,
        "mean_cer": float(mean_cer),
        "best_mean_cer": best_mean_cer,
        "plateau_rounds": plateau_rounds,
        "rule_count": tune_stats.get("rules", 0),
        "state": str(out_state),
    }
