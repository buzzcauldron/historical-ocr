"""Print doc_type routing hints."""

from __future__ import annotations

import json
from pathlib import Path

from historical_ocr.lib.type_routing import (
    fingerprint_era_hint,
    load_fingerprint_summary,
)
from historical_ocr.models.manifest import FingerprintSummary, JobManifest


def test_fingerprint_era_hint_fraktur() -> None:
    summary = FingerprintSummary(
        type_case_matches=[{"name": "German Fraktur", "era": "early_modern"}],
        suggested_material="print",
    )
    assert fingerprint_era_hint(summary) == "fraktur"


def test_load_fingerprint_summary_list(tmp_path: Path) -> None:
    data = [{"typeface": "blackletter", "score": 0.9}]
    (tmp_path / "fingerprints.json").write_text(json.dumps(data), encoding="utf-8")
    summary = load_fingerprint_summary(tmp_path)
    assert summary is not None
    assert len(summary.type_case_matches) == 1


def test_doc_type_from_hints_uses_year(tmp_path: Path) -> None:
    from historical_ocr.lib.type_routing import doc_type_from_hints

    manifest = JobManifest(job_id="t", publication_year=1850)
    name = doc_type_from_hints(manifest=manifest, language="en")
    assert name == "nineteenth_century"
