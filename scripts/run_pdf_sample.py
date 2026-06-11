#!/usr/bin/env python3
"""Extract random PDF pages, run high-quality OCR, emit per-page png/txt + timing."""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from historical_ocr.document_types.print_types import load_print_doc_type  # noqa: E402
from historical_ocr.ocr.preprocess import preprocess_for_ocr  # noqa: E402

_PAGE_STATS = re.compile(
    r"page-stats: page=(?P<page>\S+) (?P<elapsed>[0-9.]+)s .*?"
    r"time=ink:(?P<ink>[0-9.]+)s ocr:(?P<ocr>[0-9.]+)s post:(?P<post>[0-9.]+)s"
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_pages(pdf: Path, indices: list[int], out_dir: Path, *, dpi: int = 300) -> list[Path]:
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    try:
        paths: list[Path] = []
        for idx in indices:
            pix = doc[idx].get_pixmap(dpi=dpi, alpha=False)
            out = out_dir / f"{pdf.stem}_p{idx:04d}.png"
            pix.pil_save(str(out), format="PNG")
            paths.append(out)
        return paths
    finally:
        doc.close()


def write_preprocessed(images: list[Path], out_dir: Path, preprocess: dict) -> list[Path]:
    if not preprocess:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for img in images:
        prepped = preprocess_for_ocr(img, preprocess)
        dest = out_dir / f"{img.stem}_preprocessed.png"
        prepped.save(dest, format="PNG")
        written.append(dest)
    return written


def parse_page_stats(log_text: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for m in _PAGE_STATS.finditer(log_text):
        stats[m.group("page")] = {
            "elapsed_s": float(m.group("elapsed")),
            "ink_s": float(m.group("ink")),
            "ocr_s": float(m.group("ocr")),
            "post_s": float(m.group("post")),
        }
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--job-id", required=True)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--print-doc-type", default="twentieth_century")
    ap.add_argument("--publication-year", type=int, default=None)
    ap.add_argument("--quality", default="high")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file():
        print(f"error: not found: {pdf}", file=sys.stderr)
        return 1

    import fitz

    with fitz.open(str(pdf)) as doc:
        n_pages = len(doc)

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    k = min(args.count, n_pages)
    indices = sorted(rng.sample(range(n_pages), k))

    job_root = REPO / "jobs" / args.job_id
    sample_dir = job_root / "sample"
    pages_dir = sample_dir / "pages"
    pre_dir = sample_dir / "preprocessed"

    spec = load_print_doc_type(args.print_doc_type)
    images = extract_pages(pdf, indices, pages_dir, dpi=args.dpi)
    preprocessed = write_preprocessed(images, pre_dir, spec.preprocess)

    manifest = {
        "pdf": str(pdf),
        "page_count": n_pages,
        "seed": seed,
        "sample_indices": indices,
        "preprocess": spec.preprocess,
        "started_at": _utc(),
    }
    (sample_dir / "sample_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    cmd = [
        "historical-ocr",
        "run",
        args.job_id,
        "--print-doc-type",
        args.print_doc_type,
        "--quality",
        args.quality,
        "--no-extract-figures",
        "--glyph-heatmap",
    ]
    if args.publication_year:
        cmd.extend(["--publication-year", str(args.publication_year)])
    for img in images:
        cmd.extend(["-i", str(img)])

    print(f"START {_utc()}", flush=True)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    wall_s = time.perf_counter() - t0
    log = (proc.stdout or "") + (proc.stderr or "")
    print(log, end="", flush=True)
    print(f"END {_utc()}", flush=True)
    print(f"real {wall_s:.2f}", flush=True)

    if proc.returncode != 0:
        print("error: historical-ocr run failed", file=sys.stderr)
        return proc.returncode

    stats = parse_page_stats(log)
    export_dir = sample_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    job_export = job_root / "export" / "_internal"
    per_page: list[dict] = []
    for idx, img in enumerate(images):
        page_id_guess = f"{pdf.stem}_p{idx:04d}"
        # Match manifest page ids from run (stem-based)
        txt_src = job_export / "txt"
        review_src = job_export / "review"
        txt_file = next(txt_src.glob(f"*{img.stem}*.txt"), None) if txt_src.is_dir() else None
        if txt_file is None and txt_src.is_dir():
            txt_files = sorted(txt_src.glob("*.txt"))
            txt_file = txt_files[idx] if idx < len(txt_files) else None

        page_id = txt_file.stem if txt_file else page_id_guess
        page_stat = stats.get(page_id, {})

        out_png = export_dir / f"{page_id}.png"
        out_pre = export_dir / f"{page_id}.preprocessed.png"
        out_txt = export_dir / f"{page_id}.txt"
        out_review = export_dir / f"{page_id}.review.png"

        out_png.write_bytes(img.read_bytes())
        pre_src = pre_dir / f"{img.stem}_preprocessed.png"
        if pre_src.is_file():
            out_pre.write_bytes(pre_src.read_bytes())
        if txt_file and txt_file.is_file():
            out_txt.write_text(txt_file.read_text(encoding="utf-8"), encoding="utf-8")

        review_file = review_src / f"{page_id}.review.png" if review_src.is_dir() else None
        if review_file and review_file.is_file():
            out_review.write_bytes(review_file.read_bytes())

        per_page.append(
            {
                "pdf_page_index": indices[idx],
                "page_id": page_id,
                "started_at": manifest["started_at"],
                "finished_at": _utc(),
                **page_stat,
                "files": {
                    "png": str(out_png.relative_to(job_root)),
                    "preprocessed_png": str(out_pre.relative_to(job_root)) if out_pre.is_file() else None,
                    "txt": str(out_txt.relative_to(job_root)) if out_txt.is_file() else None,
                    "review_png": str(out_review.relative_to(job_root)) if out_review.is_file() else None,
                },
            },
        )

    report = {
        **manifest,
        "finished_at": _utc(),
        "wall_s": round(wall_s, 2),
        "quality": args.quality,
        "pages": per_page,
    }
    report_path = sample_dir / "timing_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
