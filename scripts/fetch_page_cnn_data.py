#!/usr/bin/env python3
"""Fetch page-CNN training images from HF datasets, OCRDatasets, and Akdeniz GT."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from historical_ocr.ml.page_cnn_datasets import (  # noqa: E402
    count_labeled,
    fetch_sources,
    list_sources,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("data/page_cnn"))
    ap.add_argument(
        "--source",
        action="append",
        help="HF source id (ocr-quality, ocr-pdf-degraded, pixparse-pdfa, pixparse-idl)",
    )
    ap.add_argument(
        "--ocrdatasets",
        action="append",
        help="OCRDatasets catalog id (iam-histdb, pinkas, sleukrith, mthv2, iam-online)",
    )
    ap.add_argument(
        "--akdeniz-gt",
        action="append",
        help="Akdeniz GT id (akdeniz-kraken-vatlib, akdeniz-kraken-cp40, akdeniz-deed-finetune)",
    )
    ap.add_argument("--ocrdatasets-root", type=Path, help="Clone of xinke-wang/OCRDatasets or data parent")
    ap.add_argument("--akdeniz-home", type=Path, help="Akdeniz $HOME (default: AKDENIZ_HOME or ~)")
    ap.add_argument(
        "--extra",
        action="append",
        metavar="LABEL:PATH",
        help="Add local images: print:/path or manuscript:/path",
    )
    ap.add_argument("--limit", type=int, default=None, help="Override per-source cap")
    ap.add_argument("--all-hf", action="store_true", help="Fetch all Hugging Face sources in registry")
    ap.add_argument("--list", action="store_true", help="List registry sources and exit")
    args = ap.parse_args()

    if args.list:
        for spec in list_sources():
            print(f"{spec.source_id:24} {spec.kind:12} {spec.label:10} limit={spec.default_limit}")
            if spec.notes:
                print(f"  {spec.notes}")
        return 0

    extra: list[tuple[Path, str]] = []
    for item in args.extra or []:
        label, _, path = item.partition(":")
        if label not in ("print", "manuscript") or not path:
            print(f"error: bad --extra {item!r} (want print:/path or manuscript:/path)", file=sys.stderr)
            return 1
        extra.append((Path(path).expanduser().resolve(), label))  # type: ignore[arg-type]

    out = args.out.expanduser().resolve()
    counts = fetch_sources(
        out,
        hf_sources=args.source,
        ocrdatasets_sources=args.ocrdatasets,
        remote_gt_sources=args.akdeniz_gt,
        ocrdatasets_root=args.ocrdatasets_root.expanduser().resolve() if args.ocrdatasets_root else None,
        akdeniz_home=args.akdeniz_home.expanduser().resolve() if args.akdeniz_home else None,
        extra_dirs=extra or None,
        limit=args.limit,
        all_hf=args.all_hf,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    totals = count_labeled(out)
    print(f"fetch complete → {out}")
    for sid, n in counts.items():
        print(f"  {sid}: {n}")
    print(f"on disk: {totals['print']} print, {totals['manuscript']} manuscript")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
