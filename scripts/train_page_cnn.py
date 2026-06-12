#!/usr/bin/env python3
"""Train the page material CNN (print vs manuscript)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from historical_ocr.ml.page_cnn import torch_available, train_page_cnn  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("data/page_cnn"))
    ap.add_argument("--out", type=Path, default=Path("models/page_cnn.pt"))
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument(
        "--patience",
        type=int,
        default=3,
        help="Stop when val accuracy fails to improve for N epochs (0 = disabled)",
    )
    ap.add_argument(
        "--extra-data",
        action="append",
        type=Path,
        help="Extra dataset roots with print/ and manuscript/ subfolders",
    )
    args = ap.parse_args()

    if not torch_available():
        print("error: PyTorch not installed — pip install -e .", file=sys.stderr)
        return 1

    data = args.data.expanduser().resolve()
    out = args.out.expanduser().resolve()
    extra = [p.expanduser().resolve() for p in (args.extra_data or [])]
    meta = train_page_cnn(
        data,
        out,
        extra_dirs=extra or None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        image_size=args.image_size,
        patience=args.patience,
        log_fn=print,
    )
    print(f"done: {meta.path}  val_acc={meta.val_accuracy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
