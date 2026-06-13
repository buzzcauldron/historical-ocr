#!/usr/bin/env python3
"""Build ketos ground-truth manifests from tesstrain line pairs.

Reads all .png + .gt.txt pairs from the tesstrain ground-truth directory.
Excludes lines whose source page matches any record in a held-out val manifest
(newspaper_gt val split), then writes train.txt and eval.txt for ketos train.

Usage:
  python scripts/build_kraken_gt.py --gt-dir data/tesseract_train/tesstrain \
      --val-manifest data/newspaper_gt/manifest.json \
      --out data/kraken_gt
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def load_val_stems(manifest_path: Path) -> set[str]:
    """Return record stems that are in the val split of the GT manifest."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        rid
        for rid, rec in (data.get("records") or {}).items()
        if rec.get("split") == "val"
    }


def line_belongs_to_val(line_png: Path, val_stems: set[str]) -> bool:
    """Return True if the line image came from a held-out val page."""
    name = line_png.stem
    for stem in val_stems:
        if stem in name:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt-dir", type=Path, required=True,
                    help="tesstrain ground-truth directory (contains *.png + *.gt.txt)")
    ap.add_argument("--val-manifest", type=Path,
                    default=Path("data/newspaper_gt/manifest.json"),
                    help="GT manifest whose val records are excluded from training")
    ap.add_argument("--out", type=Path, default=Path("data/kraken_gt"),
                    help="Output directory for train.txt and eval.txt")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval-pages", type=int, default=200,
                    help="Number of non-val-set lines to set aside as ketos eval")
    args = ap.parse_args()

    gt_dir = args.gt_dir.expanduser().resolve()
    all_pngs = sorted(gt_dir.rglob("*.png"))
    if not all_pngs:
        print(f"[build_kraken_gt] no .png files found under {gt_dir}", file=sys.stderr)
        return 1

    val_stems = load_val_stems(args.val_manifest.expanduser().resolve())
    print(f"[build_kraken_gt] held-out val page stems: {len(val_stems)}", file=sys.stderr)

    held_out: list[Path] = []
    train_pool: list[Path] = []
    for p in all_pngs:
        gt_txt = p.with_suffix(".gt.txt")
        if not gt_txt.is_file():
            continue
        if line_belongs_to_val(p, val_stems):
            held_out.append(p)
        else:
            train_pool.append(p)

    print(
        f"[build_kraken_gt] {len(train_pool)} train-pool lines, "
        f"{len(held_out)} held-out val lines",
        file=sys.stderr,
    )

    rng = random.Random(args.seed)
    rng.shuffle(train_pool)
    n_eval = min(args.eval_pages, max(1, len(train_pool) // 10))
    eval_lines = train_pool[:n_eval]
    train_lines = train_pool[n_eval:]

    print(
        f"[build_kraken_gt] split → {len(train_lines)} train / {len(eval_lines)} eval "
        f"(+ {len(held_out)} held-out newspaper_gt val)",
        file=sys.stderr,
    )

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "train.txt").write_text(
        "\n".join(str(p) for p in train_lines) + "\n", encoding="utf-8"
    )
    (out_dir / "eval.txt").write_text(
        "\n".join(str(p) for p in eval_lines) + "\n", encoding="utf-8"
    )
    (out_dir / "held_out.txt").write_text(
        "\n".join(str(p) for p in held_out) + "\n", encoding="utf-8"
    )

    stats = {
        "train_lines": len(train_lines),
        "eval_lines": len(eval_lines),
        "held_out_lines": len(held_out),
        "val_page_stems": sorted(val_stems),
        "gt_dir": str(gt_dir),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[build_kraken_gt] written to {out_dir}", file=sys.stderr)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
