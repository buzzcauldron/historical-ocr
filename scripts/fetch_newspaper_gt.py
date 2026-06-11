#!/usr/bin/env python3
"""Fetch Chronicling America newspaper pages + OCR text for train/val GT."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from historical_ocr.ml.newspaper_gt import CHRONAM_REPO, fetch_newspaper_gt  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("data/newspaper_gt"))
    ap.add_argument("--limit", type=int, default=500, help="Max new pages to download")
    ap.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
        help="Fraction held out for validation (deterministic by record id + seed)",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--text-only",
        action="store_true",
        help="Save OCR text + metadata only (skip page images)",
    )
    ap.add_argument(
        "--shard",
        type=int,
        default=None,
        metavar="N",
        help="Use only parquet shard N (0-3) for a smaller/faster sample",
    )
    args = ap.parse_args()

    shards = None
    if args.shard is not None:
        if not 0 <= args.shard <= 3:
            print("error: --shard must be 0-3", file=sys.stderr)
            return 1
        shards = [f"data/train-{args.shard:05d}-of-00004.parquet"]

    print(f"source: {CHRONAM_REPO}", file=sys.stderr)
    stats = fetch_newspaper_gt(
        args.out,
        limit=args.limit,
        val_ratio=args.val_ratio,
        seed=args.seed,
        skip_images=args.text_only,
        shards=shards,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(f"fetch complete → {args.out.expanduser().resolve()}")
    print(
        f"  this run: {stats['saved']} saved "
        f"({stats['train']} train, {stats['val']} val)",
    )
    print(
        f"  on disk: {stats['total_train']} train, {stats['total_val']} val",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
