#!/usr/bin/env python3
"""Merge newspaper GT corpora into data/newspaper_ocr for Kraken training."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from historical_ocr.ml.newspaper_train import (  # noqa: E402
    CorpusSource,
    DEFAULT_TRAIN_ROOT,
    prepare_training_corpus,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_TRAIN_ROOT)
    ap.add_argument("--ca", type=Path, default=Path("data/newspaper_gt"))
    ap.add_argument("--user", type=Path, default=Path("data/user_gt"))
    ap.add_argument("--extra", action="append", metavar="NAME:PATH", help="Extra corpus prefix:path")
    args = ap.parse_args()

    sources = [
        CorpusSource("chronicling_america", args.ca, "ca"),
        CorpusSource("user_corrections", args.user, "user"),
    ]
    for item in args.extra or []:
        name, _, path = item.partition(":")
        if not name or not path:
            print(f"error: bad --extra {item!r}", file=sys.stderr)
            return 1
        sources.append(CorpusSource(name, Path(path), name.replace("/", "_")[:12]))

    manifest = prepare_training_corpus(
        args.out,
        sources=sources,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(f"prepared → {args.out.expanduser().resolve()}")
    print(f"  train: {manifest['counts']['train']}  val: {manifest['counts']['val']}")
    return 0 if manifest["counts"]["train"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
