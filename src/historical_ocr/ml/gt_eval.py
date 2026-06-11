"""LLM-independent OCR on newspaper GT corpora + CER/WER scoring."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from historical_ocr.config import Settings
from historical_ocr.document_types.print_types import apply_print_doc_type, load_print_doc_type
from historical_ocr.lib.quality_presets import DEFAULT_QUALITY_TIER, QualityTier, apply_tier_for_run
from historical_ocr.lib.rules_only import rules_only_clean
from historical_ocr.ml.newspaper_gt import load_manifest

SplitName = Literal["train", "val", "all"]
EvalPreset = QualityTier


@dataclass(frozen=True)
class EvalPageResult:
    record_id: str
    split: str
    cer: float
    wer: float
    ref_chars: int
    ref_words: int
    hypothesis_path: str | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_for_eval(text: str) -> str:
    """Loose normalization for OCR metric comparison."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.casefold()
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def character_error_rate(reference: str, hypothesis: str) -> tuple[float, int]:
    ref = normalize_for_eval(reference)
    hyp = normalize_for_eval(hypothesis)
    if not ref:
        return (0.0 if not hyp else 1.0), 0
    dist = _levenshtein(ref, hyp)
    return dist / len(ref), len(ref)


def word_error_rate(reference: str, hypothesis: str) -> tuple[float, int]:
    ref_words = normalize_for_eval(reference).split()
    hyp_words = normalize_for_eval(hypothesis).split()
    if not ref_words:
        return (0.0 if not hyp_words else 1.0), 0
    dist = _levenshtein(" ".join(ref_words), " ".join(hyp_words))
    # Word-level edit distance via token join is approximate; use char dist on joined tokens
    # for a stable proxy when whitespace differs.
    return dist / max(len(" ".join(ref_words)), 1), len(ref_words)


def _year_from_meta(meta: dict[str, Any]) -> int | None:
    raw = str(meta.get("issue_date") or "")
    m = re.match(r"(\d{4})", raw)
    return int(m.group(1)) if m else None


def ocr_page_with_preset(
    image: Path,
    *,
    publication_year: int | None = None,
    preset: EvalPreset = DEFAULT_QUALITY_TIER,
    settings: Settings | None = None,
) -> str:
    """Run print OCR using the same quality tier as production (no LLM)."""
    from historical_ocr.pipeline.print_selector import run_tesseract_backend

    s = apply_tier_for_run(settings or Settings(), preset)
    s = s.model_copy(
        update={
            "save_layout_artifacts": False,
            "symbol_glyph_heatmap": False,
            "export_internal": False,
            "tei_facsimile": False,
        },
    )
    spec = None
    if publication_year is not None:
        s = s.model_copy(update={"publication_year": publication_year})
        from historical_ocr.document_types.print_types import suggest_print_doc_type

        name = suggest_print_doc_type(year=publication_year)
        spec = load_print_doc_type(name)
        s = apply_print_doc_type(s, spec)

    lang = spec.tesseract_lang if spec else s.tesseract_lang
    psm = spec.tesseract_psm if spec else 6
    preprocess = spec.preprocess if spec else {}
    layout = run_tesseract_backend(
        image,
        lang=lang,
        psm=psm,
        preprocess=preprocess,
        settings=s,
        print_spec=spec,
    )
    return rules_only_clean(layout.full_text, s)


def ocr_page_rules_only(
    image: Path,
    *,
    publication_year: int | None = None,
    settings=None,
) -> str:
    """Backward-compatible alias — uses the default (medium) preset."""
    return ocr_page_with_preset(
        image,
        publication_year=publication_year,
        preset=DEFAULT_QUALITY_TIER,
        settings=settings,
    )


def _iter_gt_records(
    gt_dir: Path,
    *,
    split: SplitName,
    limit: int | None,
) -> list[tuple[str, dict[str, Any]]]:
    manifest = load_manifest(gt_dir)
    records = manifest.get("records") or {}
    rows: list[tuple[str, dict[str, Any]]] = []
    for record_id, rec in records.items():
        if split != "all" and rec.get("split") != split:
            continue
        rows.append((record_id, rec))
    rows.sort(key=lambda x: x[0])
    if limit is not None:
        rows = rows[:limit]
    return rows


def eval_newspaper_gt(
    gt_dir: Path,
    *,
    split: SplitName = "val",
    limit: int | None = None,
    out_dir: Path | None = None,
    preset: EvalPreset = DEFAULT_QUALITY_TIER,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """OCR GT images with a quality preset and score against reference text (no LLM)."""
    gt_dir = gt_dir.expanduser().resolve()
    run_dir = (out_dir or gt_dir / "eval" / _now_iso().replace(":", "-")).expanduser().resolve()
    pred_dir = run_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    from historical_ocr.document_types.print_types import suggest_print_doc_type

    page_results: list[dict[str, Any]] = []
    cer_sum = 0.0
    wer_sum = 0.0
    scored = 0
    by_doc_type: dict[str, dict[str, Any]] = {}

    for record_id, rec in _iter_gt_records(gt_dir, split=split, limit=limit):
        split_name = str(rec.get("split") or "train")
        stem = str(rec.get("stem") or record_id.replace("/", "_"))
        ref_path = gt_dir / str(rec["text"])
        meta_path = gt_dir / str(rec["meta"])
        image_rel = rec.get("image")
        image_path = gt_dir / str(image_rel) if image_rel else None

        if not ref_path.is_file():
            page_results.append({"record_id": record_id, "error": f"missing ref: {ref_path}"})
            continue
        if not image_path or not image_path.is_file():
            page_results.append({"record_id": record_id, "error": "missing image"})
            continue

        reference = ref_path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        year = _year_from_meta(meta)
        doc_type = suggest_print_doc_type(year=year) if year else "unknown"

        _log(f"ocr: {record_id} ({split_name}, {doc_type})")
        try:
            hypothesis = ocr_page_with_preset(
                image_path,
                publication_year=year,
                preset=preset,
            )
            pred_path = pred_dir / f"{stem}.txt"
            pred_path.write_text(hypothesis + "\n", encoding="utf-8")
            cer, ref_chars = character_error_rate(reference, hypothesis)
            wer, ref_words = word_error_rate(reference, hypothesis)
            cer_sum += cer
            wer_sum += wer
            scored += 1
            bucket = by_doc_type.setdefault(
                doc_type,
                {"scored": 0, "cer_sum": 0.0, "wer_sum": 0.0},
            )
            bucket["scored"] += 1
            bucket["cer_sum"] += cer
            bucket["wer_sum"] += wer
            page_results.append(
                {
                    "record_id": record_id,
                    "split": split_name,
                    "doc_type": doc_type,
                    "publication_year": year,
                    "cer": round(cer, 6),
                    "wer": round(wer, 6),
                    "ref_chars": ref_chars,
                    "ref_words": ref_words,
                    "hypothesis": str(pred_path.relative_to(run_dir)),
                    "image": str(image_path.relative_to(gt_dir)),
                },
            )
        except Exception as exc:
            page_results.append({"record_id": record_id, "error": str(exc)})

    doc_type_summary = {
        name: {
            "scored": int(vals["scored"]),
            "mean_cer": round(vals["cer_sum"] / vals["scored"], 6),
            "mean_wer": round(vals["wer_sum"] / vals["scored"], 6),
        }
        for name, vals in sorted(by_doc_type.items())
        if vals["scored"]
    }
    report = {
        "version": 1,
        "gt_dir": str(gt_dir),
        "split": split,
        "limit": limit,
        "scored": scored,
        "mean_cer": round(cer_sum / scored, 6) if scored else None,
        "mean_wer": round(wer_sum / scored, 6) if scored else None,
        "by_doc_type": doc_type_summary,
        "preset": preset,
        "rules_only": True,
        "at": _now_iso(),
        "pages": page_results,
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _log(f"report → {report_path}")
    if scored:
        _log(
            f"[{preset}] mean CER {report['mean_cer']:.4f}  "
            f"mean WER {report['mean_wer']:.4f} ({scored} pages)",
        )
        for name, vals in doc_type_summary.items():
            _log(
                f"  {name}: CER {vals['mean_cer']:.4f}  "
                f"WER {vals['mean_wer']:.4f} ({vals['scored']} pages)",
            )
    return report


def validate_newspaper_accuracy(
    gt_dir: Path,
    *,
    split: SplitName = "val",
    limit: int | None = None,
    presets: tuple[EvalPreset, ...] = ("free", "medium"),
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Compare quality presets on the same GT split; medium is the production default."""
    gt_dir = gt_dir.expanduser().resolve()
    stamp = _now_iso().replace(":", "-")
    results: dict[str, Any] = {}
    best_preset = DEFAULT_QUALITY_TIER
    best_cer = None

    for preset in presets:
        report = eval_newspaper_gt(
            gt_dir,
            split=split,
            limit=limit,
            out_dir=gt_dir / "eval" / f"validate_{preset}_{stamp}",
            preset=preset,
            log_fn=log_fn,
        )
        results[preset] = {
            "scored": report["scored"],
            "mean_cer": report["mean_cer"],
            "mean_wer": report["mean_wer"],
        }
        cer = report.get("mean_cer")
        if cer is not None and (best_cer is None or cer < best_cer):
            best_cer = cer
            best_preset = preset

    summary = {
        "version": 1,
        "gt_dir": str(gt_dir),
        "split": split,
        "limit": limit,
        "presets": results,
        "best_preset": best_preset,
        "production_preset": DEFAULT_QUALITY_TIER,
        "at": _now_iso(),
    }
    out_path = gt_dir / "eval" / f"validate_summary_{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if log_fn:
        log_fn(f"validate summary → {out_path}")
        log_fn(f"best on split: {best_preset} (CER {best_cer:.4f})" if best_cer is not None else "no scores")
    summary["summary_path"] = str(out_path)
    return summary
