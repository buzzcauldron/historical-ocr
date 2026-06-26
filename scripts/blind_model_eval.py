#!/usr/bin/env python3
"""Blind model comparison — no peeking at training metrics, score on held-out GT."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compare_page_cnn(candidates: list[Path], gt_dir: Path) -> dict:
    from historical_ocr.ml.gt_eval import _iter_gt_records
    from historical_ocr.ml.page_cnn import load_checkpoint, predict_image

    images: list[Path] = []
    for _rid, rec in _iter_gt_records(gt_dir, split="val", limit=None):
        img = rec.get("image")
        if img:
            p = gt_dir / str(img)
            if p.is_file():
                images.append(p)
    if not images:
        return {"error": "no val images"}

    results: dict[str, dict] = {}
    for model_path in candidates:
        if not model_path.is_file():
            results[str(model_path)] = {"error": "missing"}
            continue
        model, meta = load_checkpoint(model_path)
        correct = 0
        conf_sum = 0.0
        for img in images:
            label, score = predict_image(model, meta, img)
            if label == "print":
                correct += 1
            conf_sum += score
        n = len(images)
        results[str(model_path)] = {
            "pages": n,
            "print_accuracy": round(correct / n, 6),
            "mean_print_confidence": round(conf_sum / n, 6),
            "checkpoint_val_acc": meta.val_accuracy,
        }
    return {"task": "page_cnn", "images": len(images), "models": results}


def eval_ocr_preset(
    gt_dir: Path,
    *,
    split: str = "val",
    limit: int | None = None,
    preset: str = "medium",
    label: str = "baseline",
    settings=None,
) -> dict:
    from historical_ocr.ml.gt_eval import eval_newspaper_gt

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = gt_dir / "eval" / f"blind_{label}_{stamp}"
    report = eval_newspaper_gt(
        gt_dir,
        split=split,  # type: ignore[arg-type]
        limit=limit,
        out_dir=out,
        preset=preset,  # type: ignore[arg-type]
        settings=settings,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    return {
        "label": label,
        "preset": preset,
        "scored": report.get("scored"),
        "mean_cer": report.get("mean_cer"),
        "mean_wer": report.get("mean_wer"),
        "report": str(out / "report.json"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Blind model comparison on newspaper GT val")
    ap.add_argument("--gt-dir", type=Path, default=ROOT / "data" / "newspaper_gt")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "benchmarks" / "blind_eval")
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--histnews", type=Path, default=ROOT / "models" / "histnews.traineddata")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary: dict = {"at": _now(), "gt_dir": str(args.gt_dir), "comparisons": []}

    # Page CNN: candidate vs any local baseline
    candidates = [
        ROOT / "models" / "page_cnn.pt",
        ROOT / "models" / "page_cnn_test.pt",
    ]
    cnn = compare_page_cnn(candidates, args.gt_dir)
    summary["page_cnn"] = cnn
    print(json.dumps(cnn, indent=2))

    if not args.skip_ocr:
        from historical_ocr.config import Settings

        baseline = eval_ocr_preset(
            args.gt_dir,
            limit=args.limit,
            preset="medium",
            label="medium_eng",
        )
        summary["comparisons"].append(baseline)
        print(json.dumps(baseline, indent=2))

        if args.histnews.is_file():
            tessdata = args.histnews.parent / "tessdata"
            tessdata.mkdir(exist_ok=True)
            dest = tessdata / args.histnews.name
            if not dest.is_file():
                import shutil
                shutil.copy2(args.histnews, dest)
            s = Settings().model_copy(
                update={
                    "tesseract_finetune_lang": "histnews",
                    "tesseract_finetune_path": args.histnews,
                    "tessdata_prefix": tessdata,
                },
            )
            hist = eval_ocr_preset(
                args.gt_dir,
                limit=args.limit,
                preset="medium",
                label="medium_histnews",
                settings=s,
            )
            summary["comparisons"].append(hist)
            print(json.dumps(hist, indent=2))

    # Pick winners
    if cnn.get("models"):
        ranked = sorted(
            ((k, v) for k, v in cnn["models"].items() if "print_accuracy" in v),
            key=lambda kv: (kv[1]["print_accuracy"], kv[1]["mean_print_confidence"]),
            reverse=True,
        )
        if ranked:
            summary["page_cnn_winner"] = ranked[0][0]

    ocr_rows = [c for c in summary.get("comparisons", []) if c.get("mean_cer") is not None]
    if ocr_rows:
        best = min(ocr_rows, key=lambda c: c["mean_cer"])
        summary["ocr_winner"] = best["label"]
        summary["ocr_best_cer"] = best["mean_cer"]

    out_path = args.out / f"blind_{stamp}.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nblind summary → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
