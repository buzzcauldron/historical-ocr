"""Human-corrected OCR text → tuning corpus + learned replacement rules."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

DEFAULT_CORPUS = Path("data/user_gt")
_RULES_NAME = "tuned_rules.json"
_WORD_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True)
class TuneRule:
    src: str
    dst: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        return {"from": self.src, "to": self.dst, "count": self.count}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def corpus_manifest_path(corpus: Path) -> Path:
    return corpus / "manifest.json"


def load_corpus_manifest(corpus: Path) -> dict[str, Any]:
    path = corpus_manifest_path(corpus)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "source": "user_corrections", "records": {}, "counts": {"train": 0, "val": 0}}


def save_corpus_manifest(corpus: Path, manifest: dict[str, Any]) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    corpus_manifest_path(corpus).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _split_dirs(corpus: Path, split: str) -> tuple[Path, Path, Path, Path]:
    base = corpus / split
    return base / "images", base / "text", base / "raw", base / "meta"


def _sanitize_id(record_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", record_id.strip())[:120] or "page"


def submit_correction(
    corpus: Path,
    *,
    record_id: str,
    image_src: Path,
    raw_text: str,
    corrected_text: str,
    split: str = "train",
    meta: dict[str, Any] | None = None,
) -> Path:
    """Store image + raw OCR + human-corrected text in the tuning corpus."""
    corpus = corpus.expanduser().resolve()
    if not corrected_text.strip():
        raise ValueError("corrected text is empty")
    if not image_src.is_file():
        raise FileNotFoundError(image_src)

    rid = _sanitize_id(record_id)
    img_dir, text_dir, raw_dir, meta_dir = _split_dirs(corpus, split)
    for d in (img_dir, text_dir, raw_dir, meta_dir):
        d.mkdir(parents=True, exist_ok=True)

    ext = image_src.suffix.lower() or ".jpg"
    image_dest = img_dir / f"{rid}{ext}"
    if image_src.resolve() != image_dest.resolve():
        shutil.copy2(image_src, image_dest)

    text_path = text_dir / f"{rid}.txt"
    raw_path = raw_dir / f"{rid}.txt"
    meta_path = meta_dir / f"{rid}.json"

    text_path.write_text(corrected_text.rstrip() + "\n", encoding="utf-8")
    raw_path.write_text(raw_text.rstrip() + "\n", encoding="utf-8")
    payload = {
        "record_id": rid,
        "split": split,
        "submitted_at": _now_iso(),
        **(meta or {}),
    }
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    manifest = load_corpus_manifest(corpus)
    manifest["records"][rid] = {
        "split": split,
        "stem": rid,
        "text": str(text_path.relative_to(corpus)),
        "raw": str(raw_path.relative_to(corpus)),
        "meta": str(meta_path.relative_to(corpus)),
        "image": str(image_dest.relative_to(corpus)),
    }
    manifest["counts"] = {
        "train": sum(1 for r in manifest["records"].values() if r["split"] == "train"),
        "val": sum(1 for r in manifest["records"].values() if r["split"] == "val"),
    }
    save_corpus_manifest(corpus, manifest)
    return text_path


def _job_raw_text(job_root: Path, page_id: str, basename: str) -> str:
    for rel in (
        f"clean/{page_id}.txt",
        f"ocr/{page_id}.txt",
        f"export/{basename}.txt",
    ):
        path = job_root / rel
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"no OCR text for {page_id} under {job_root}")


def submit_from_job(
    job_id: str,
    *,
    jobs_dir: Path,
    corpus: Path = DEFAULT_CORPUS,
    corrected_path: Path | None = None,
    split: str = "train",
    log_fn: Callable[[str], None] | None = None,
) -> list[Path]:
    """Import user-corrected text from a completed job (export/*.corrected.txt)."""
    from historical_ocr.lib.export_names import resolve_export_basename
    from historical_ocr.models.manifest import JobManifest

    job_root = (jobs_dir / job_id).expanduser().resolve()
    if not job_root.is_dir():
        raise FileNotFoundError(job_root)

    manifest_path = job_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    job_manifest = JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    basename = resolve_export_basename(job_manifest)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    pairs: list[tuple[str, Path]] = []
    if corrected_path is not None:
        pairs.append((basename, corrected_path.expanduser().resolve()))
    else:
        export_dir = job_root / "export"
        for path in sorted(export_dir.glob("*.corrected.txt")):
            pairs.append((path.name[: -len(".corrected.txt")], path))
        if not pairs:
            default = export_dir / f"{basename}.corrected.txt"
            if default.is_file():
                pairs.append((basename, default))

    if not pairs:
        raise FileNotFoundError(
            f"no corrected text found — save edits as export/{basename}.corrected.txt "
            f"or pass --corrected PATH",
        )

    saved: list[Path] = []
    pages_by_stem: dict[str, Any] = {}
    for page in job_manifest.pages:
        stem = page.page_id
        if "_p" in stem and stem.rsplit("_p", 1)[-1].isdigit():
            stem = stem.rsplit("_p", 1)[0]
        pages_by_stem.setdefault(stem, page)
        pages_by_stem[page.page_id] = page

    for stem, corr in pairs:
        page = pages_by_stem.get(stem) or (job_manifest.pages[0] if len(job_manifest.pages) == 1 else None)
        if page is None:
            raise ValueError(f"cannot map corrected file {corr.name} to a job page")
        image = job_root / page.image_path
        raw = _job_raw_text(job_root, page.page_id, basename)
        corrected = corr.read_text(encoding="utf-8")
        _log(f"submit: {stem} ← {corr.name}")
        dest = submit_correction(
            corpus,
            record_id=stem,
            image_src=image,
            raw_text=raw,
            corrected_text=corrected,
            split=split,
            meta={
                "job_id": job_id,
                "page_id": page.page_id,
                "corrected_file": str(corr),
                "basename": basename,
            },
        )
        saved.append(dest)
    return saved


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _mine_replace_ops(raw: str, corrected: str) -> list[tuple[str, str]]:
    raw_tokens = _tokenize(raw)
    cor_tokens = _tokenize(corrected)
    if not raw_tokens or not cor_tokens:
        return []

    sm = SequenceMatcher(None, raw_tokens, cor_tokens)
    ops: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        src = " ".join(raw_tokens[i1:i2])
        dst = " ".join(cor_tokens[j1:j2])
        if not src or not dst or src == dst:
            continue
        if len(src) > 80 or len(dst) > 80:
            continue
        ops.append((src, dst))
    return ops


def mine_tune_rules(
    corpus: Path,
    *,
    min_count: int = 1,
) -> list[TuneRule]:
    """Extract repeated raw→corrected replacements from the user corpus."""
    corpus = corpus.expanduser().resolve()
    manifest = load_corpus_manifest(corpus)
    counts: dict[tuple[str, str], int] = {}

    for rec in manifest.get("records", {}).values():
        raw_path = corpus / str(rec["raw"])
        text_path = corpus / str(rec["text"])
        if not raw_path.is_file() or not text_path.is_file():
            continue
        raw = raw_path.read_text(encoding="utf-8")
        corrected = text_path.read_text(encoding="utf-8")
        for pair in _mine_replace_ops(raw, corrected):
            counts[pair] = counts.get(pair, 0) + 1

    rules = [
        TuneRule(src=src, dst=dst, count=n)
        for (src, dst), n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        if n >= min_count and src != dst
    ]
    # Longer patterns first to avoid clobbering shorter prefixes.
    rules.sort(key=lambda r: (-len(r.src), -r.count, r.src))
    return rules


def rules_path(corpus: Path) -> Path:
    return corpus.expanduser().resolve() / _RULES_NAME


def save_tune_rules(corpus: Path, rules: list[TuneRule]) -> Path:
    corpus = corpus.expanduser().resolve()
    path = rules_path(corpus)
    payload = {
        "version": 1,
        "generated_at": _now_iso(),
        "rule_count": len(rules),
        "rules": [r.as_dict() for r in rules],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_tune_rules(path: Path | None) -> list[TuneRule]:
    if path is None or not path.expanduser().is_file():
        return []
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    rows = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[TuneRule] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = str(row.get("from") or row.get("src") or "").strip()
        dst = str(row.get("to") or row.get("dst") or "").strip()
        if src and dst:
            out.append(TuneRule(src=src, dst=dst, count=int(row.get("count", 1))))
    out.sort(key=lambda r: (-len(r.src), -r.count, r.src))
    return out


def apply_tune_rules(text: str, rules: list[TuneRule]) -> str:
    """Apply mined replacement rules (longest match first)."""
    if not rules:
        return text
    for rule in rules:
        if " " in rule.src:
            text = text.replace(rule.src, rule.dst)
        else:
            text = re.sub(rf"\b{re.escape(rule.src)}\b", rule.dst, text)
    return text


def tune_corpus(
    corpus: Path,
    *,
    min_count: int = 1,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    rules = mine_tune_rules(corpus, min_count=min_count)
    path = save_tune_rules(corpus, rules)
    if log_fn:
        log_fn(f"tuned {len(rules)} rules → {path}")
    return {"rules": len(rules), "path": str(path)}
