"""Training circle: run → correct → teach (submit + tune rules)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from historical_ocr.config import Settings
from historical_ocr.ml.user_corrections import (
    DEFAULT_CORPUS,
    load_tune_rules,
    rules_path,
    submit_from_job,
    tune_corpus,
)


def correction_template_path(job_id: str, settings: Settings | None = None) -> Path | None:
    from historical_ocr.lib.export_names import production_paths, resolve_export_basename
    from historical_ocr.models.manifest import JobManifest

    s = settings or Settings()
    job_root = (s.jobs_dir / job_id).expanduser().resolve()
    manifest_path = job_root / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    basename = resolve_export_basename(manifest)
    export_txt = production_paths(job_root / "export", basename)["txt"]
    if not export_txt.is_file():
        return None
    dest = export_txt.with_name(f"{basename}.corrected.txt")
    if not dest.is_file():
        dest.write_text(export_txt.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def teach_from_job(
    job_id: str,
    *,
    settings: Settings | None = None,
    corpus: Path = DEFAULT_CORPUS,
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    """Import corrections from a job and mine tune rules."""
    s = settings or Settings()

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    _log(f"teach: submit corrections from {job_id}")
    submit_from_job(job_id, jobs_dir=s.jobs_dir, corpus=corpus, log_fn=_log)
    stats = tune_corpus(corpus, log_fn=_log)
    return stats


def tune_rule_count(corpus: Path = DEFAULT_CORPUS) -> int:
    path = rules_path(corpus)
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data.get("rules") or [])
    except (OSError, json.JSONDecodeError):
        return len(load_tune_rules(path))
