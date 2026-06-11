"""historical-ocr command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from historical_ocr import __version__
from historical_ocr.config import Settings
from historical_ocr.backends import bib_ocr as bib_backend
from historical_ocr.backends import fingerprint as fp_backend
from historical_ocr.backends import ocr_cleanup as underwood_backend
from historical_ocr.backends import page_cnn as cnn_backend
from historical_ocr.backends import tesseract as tess_backend
from historical_ocr.backends import transcriber_shell as shell_backend
from historical_ocr.pipeline.acquire import acquire_from_url, ingest_local
from historical_ocr.pipeline.export import export_job
from historical_ocr.pipeline.run_job import load_manifest, run_job


def _job_paths(settings: Settings, job_id: str):
    from historical_ocr.config import JobPaths

    return JobPaths((settings.jobs_dir / job_id).expanduser().resolve())


def cmd_run(args: argparse.Namespace) -> int:
    inputs = [Path(p) for p in (args.input or [])]
    manifest = run_job(
        args.job_id,
        url=args.url,
        limit=args.limit,
        inputs=inputs or None,
        mode=args.mode,
        prompt=Path(args.prompt) if args.prompt else None,
        fingerprint=args.fingerprint,
        clean=args.clean,
        print_doc_type=args.print_doc_type,
        ocr_combination=args.ocr_combination,
        publication_year=args.publication_year,
        print_language=args.print_language,
        extract_figures=args.extract_figures,
        fast=args.fast,
        symbol_filter=args.symbol_filter,
        glyph_heatmap=args.glyph_heatmap,
        log_fn=lambda m: print(m, file=sys.stderr, flush=True),
    )
    print(json.dumps(manifest.export, indent=2))
    return 0


def cmd_acquire(args: argparse.Namespace) -> int:
    settings = Settings()
    job = _job_paths(settings, args.job_id)
    from historical_ocr.models.manifest import JobManifest

    manifest = JobManifest(job_id=args.job_id)
    if args.url:
        acquire_from_url(
            args.url,
            job,
            manifest,
            limit=args.limit,
            log_fn=lambda m: print(m, file=sys.stderr),
        )
    for p in args.input or []:
        ingest_local([Path(p)], job, manifest)
    job.manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    print(f"job ready: {job.root}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    settings = Settings()
    job = _job_paths(settings, args.job_id)
    manifest = load_manifest(args.job_id, settings)
    paths = export_job(job, manifest)
    print(json.dumps(paths, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.job_id)
    print(manifest.model_dump_json(indent=2))
    return 0


def cmd_tools(_args: argparse.Namespace) -> int:
    settings = Settings()
    model_path = (
        settings.page_cnn_model.expanduser().resolve() if settings.page_cnn_model else None
    )
    tools = {
        "tesseract (print OCR)": tess_backend.available(),
        "bib-ocr (PDF bibliography cascade)": bib_backend.available(),
        "transcriber-shell (manuscript)": shell_backend.available(),
        "manuscript-fingerprint (type case)": fp_backend.available(),
        "ocr-cleanup / Underwood rules (print clean)": underwood_backend.available(),
        "page CNN (auto routing)": cnn_backend.available(model_path),
    }
    for name, ok in tools.items():
        print(f"{'✓' if ok else '✗'} {name}")
    if tess_backend.available():
        print(f"  → {tess_backend.describe(lang_bundle=settings.tesseract_lang)}")
        missing = tess_backend.historical_langs_missing()
        if missing:
            print(f"  → recommended packs not installed: {', '.join(missing)}")
    print(f"  → {bib_backend.describe()}")
    if model_path:
        print(f"  → {cnn_backend.describe(model_path)}")
    return 0


def cmd_bib_ocr(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.is_file():
        print(f"error: not found: {pdf}", file=sys.stderr)
        return 1
    if not bib_backend.available():
        print(f"error: {bib_backend.describe()}", file=sys.stderr)
        print("  pip install -e ../bib-ocr", file=sys.stderr)
        return 1
    result = bib_backend.extract_citations(
        pdf,
        max_stage=args.max_stage,
        verbose=args.verbose,
    )
    if args.json:
        import json

        print(json.dumps(result, indent=2, default=str))
        return 0
    for row in result.get("citations", []):
        stage = row.get("stage", "?")
        doi = row.get("doi") or ""
        text = (row.get("text") or row.get("raw") or "")[:120]
        print(f"{stage}\t{doi}\t{text}")
    print(f"stages: {', '.join(result.get('stages_run', []))}")
    print(f"total: {len(result.get('citations', []))}")
    return 0


def cmd_tesseract(args: argparse.Namespace) -> int:
    settings = Settings()
    tess_backend.configure_from_settings(settings)
    info = tess_backend.get_info()
    if not info.binary:
        print("tesseract: not found on PATH", file=sys.stderr)
        print("  macOS:  brew install tesseract tesseract-lang", file=sys.stderr)
        print("  Debian: sudo apt install tesseract-ocr poppler-utils", file=sys.stderr)
        return 1
    print(f"binary:   {info.binary}")
    print(f"version:  {info.version or '—'}")
    print(f"tessdata: {info.tessdata_dir or '—'}")
    print(f"langs:    {len(info.installed_langs)} installed")
    if args.verbose:
        for lang in info.installed_langs:
            mark = " *" if lang in tess_backend.HISTORICAL_LANGS else ""
            print(f"  {lang}{mark}")
    missing_hist = tess_backend.historical_langs_missing(installed=set(info.installed_langs))
    if missing_hist:
        print(f"historical packs missing: {', '.join(missing_hist)}")
    bundle = args.lang or settings.tesseract_lang
    missing_bundle = tess_backend.missing_langs(bundle, installed=set(info.installed_langs))
    if missing_bundle:
        print(f"missing for '{bundle}': {', '.join(missing_bundle)}")
    return 0


def cmd_cnn_train(args: argparse.Namespace) -> int:
    from historical_ocr.ml.page_cnn import torch_available, train_page_cnn

    if not torch_available():
        print("error: PyTorch not installed — pip install -e '.[ml]'", file=sys.stderr)
        return 1
    data = Path(args.data).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    extra = [Path(p).expanduser().resolve() for p in (args.extra_data or [])]
    train_page_cnn(
        data,
        out,
        extra_dirs=extra or None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        image_size=args.image_size,
        patience=args.patience,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(out)
    return 0


def cmd_cnn_sources(_args: argparse.Namespace) -> int:
    from historical_ocr.ml.page_cnn_datasets import load_registry

    reg = load_registry()
    print("Hugging Face (historical-ocr cnn fetch --source <id>):")
    for sid, raw in (reg.get("huggingface") or {}).items():
        print(f"  {sid:22} {raw['label']:10} limit={raw.get('default_limit', '?')}")
        if raw.get("citation"):
            print(f"    {raw['citation']}")
    print()
    print("OCRDatasets catalog (--ocrdatasets <id> --ocrdatasets-root PATH):")
    print("  https://github.com/xinke-wang/OCRDatasets")
    for sid, raw in (reg.get("ocrdatasets") or {}).items():
        print(f"  {sid:22} {raw['label']:10} ref={raw.get('ocrdatasets_ref', sid)}")
    print()
    print("Akdeniz GT on Bridges (--akdeniz-gt <id> or xfer script):")
    for sid, raw in (reg.get("remote_gt") or {}).items():
        print(f"  {sid:22} {raw['label']:10}")
    print()
    print("Add more data anytime:")
    print("  historical-ocr cnn fetch --extra print:/path/to/pages")
    print("  historical-ocr cnn train --extra-data /path/to/more_dataset_root")
    return 0


def cmd_cnn_fetch(args: argparse.Namespace) -> int:
    from historical_ocr.ml.page_cnn_datasets import count_labeled, fetch_sources

    out = Path(args.out).expanduser().resolve()
    extra: list[tuple[Path, str]] = []
    for item in args.extra or []:
        label, _, path = item.partition(":")
        if label not in ("print", "manuscript") or not path:
            print(
                f"error: bad --extra {item!r} (want print:/path or manuscript:/path)",
                file=sys.stderr,
            )
            return 1
        extra.append((Path(path).expanduser().resolve(), label))  # type: ignore[arg-type]

    counts = fetch_sources(
        out,
        hf_sources=args.source,
        ocrdatasets_sources=args.ocrdatasets,
        remote_gt_sources=args.akdeniz_gt,
        ocrdatasets_root=Path(args.ocrdatasets_root).expanduser().resolve()
        if args.ocrdatasets_root
        else None,
        akdeniz_home=Path(args.akdeniz_home).expanduser().resolve() if args.akdeniz_home else None,
        extra_dirs=extra or None,
        limit=args.limit,
        all_hf=args.all_hf,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    totals = count_labeled(out)
    for sid, n in counts.items():
        print(f"{sid}\t{n}")
    print(f"total\t{totals['print']} print, {totals['manuscript']} manuscript → {out}")
    return 0


def cmd_cnn_predict(args: argparse.Namespace) -> int:
    settings = Settings()
    model_path = (
        settings.page_cnn_model.expanduser().resolve() if settings.page_cnn_model else None
    )
    if not cnn_backend.available(model_path):
        print("error: set HISTORICAL_OCR_PAGE_CNN_MODEL to a trained .pt file", file=sys.stderr)
        return 1
    for image in args.image:
        path = Path(image).expanduser().resolve()
        label, score = cnn_backend.classify_page(
            path,
            model_path=model_path,  # type: ignore[arg-type]
            threshold=settings.page_cnn_threshold,
        )
        print(f"{path.name}\t{label}\t{score:.4f}")
    return 0


def cmd_print_types(_args: argparse.Namespace) -> int:
    from historical_ocr.document_types import ERA_BANDS, list_print_doc_types, load_print_doc_type

    from historical_ocr.document_types import LANGUAGE_ERA_MATRIX, list_print_languages

    print("Languages:", ", ".join(f"{x.code} ({x.label})" for x in list_print_languages()))
    print()
    print("Chronology (English; other languages use parallel matrices):")
    for band in ERA_BANDS:
        print(f"  {band.start:4}–{band.end:<4}  → {band.name}")
    for code in ("la", "de", "fr"):
        bands = LANGUAGE_ERA_MATRIX.get(code, ())
        if bands:
            print(f"  [{code}] {bands[0].start}–{bands[-1].end} → {bands[0].name} … {bands[-1].name}")
    print()
    for name in list_print_doc_types():
        try:
            spec = load_print_doc_type(name)
            print(
                f"{name:24}  {spec.era_range:12}  {spec.tesseract_lang:16}  "
                f"{spec.ocr_combination:22}  {spec.normalization_mode}",
            )
        except FileNotFoundError:
            print(name)
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    from historical_ocr.gui import main as gui_main

    gui_main()
    return 0


def cmd_convert_images(args: argparse.Namespace) -> int:
    from historical_ocr.image_tools.convert import convert_file, find_images

    sources = [Path(p).expanduser().resolve() for p in args.input]
    images = find_images(sources, recurse=args.recurse)
    if not images:
        print("error: no images found", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    fmt = args.format
    print(
        f"convert-images: {len(images)} image(s) → {fmt.upper()}"
        + ("  [DRY RUN]" if args.dry_run else ""),
        file=sys.stderr,
    )

    counts: dict[str, int] = {"converted": 0, "skipped": 0, "error": 0, "dry-run": 0}
    prefix_map = {"converted": "✓", "skipped": "–", "error": "✗", "dry-run": "?"}
    for image in images:
        status, msg = convert_file(
            image,
            out_dir=out_dir,
            fmt=fmt,
            max_width=args.max_width,
            max_height=args.max_height,
            max_pixels=args.max_pixels,
            quality=args.quality,
            keep_original=args.keep_original,
            force=args.force,
            dry_run=args.dry_run,
            scale_xml=not args.no_scale_xml,
            use_cucim=args.use_cucim,
        )
        counts[status] = counts.get(status, 0) + 1
        print(f"  {prefix_map.get(status, '?')} {msg}")

    key = "dry-run" if args.dry_run else "converted"
    print(
        f"summary: {counts[key]} converted, {counts['skipped']} skipped, {counts['error']} errors",
        file=sys.stderr,
    )
    return 1 if counts["error"] else 0


def cmd_ecosystem(_args: argparse.Namespace) -> int:
    doc = Path(__file__).resolve().parents[2] / "docs" / "ECOSYSTEM.md"
    if doc.is_file():
        print(doc.read_text(encoding="utf-8"))
    else:
        print("docs/ECOSYSTEM.md not found", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="historical-ocr",
        description=(
            "Produce computational-ready text: vendored fetch/OCR/export plus "
            "optional transcriber-shell and manuscript-fingerprint CLIs."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Full pipeline for a job")
    run.add_argument("job_id", help="Job identifier (creates jobs/<job_id>/)")
    run.add_argument("--url", help="Repository URL to fetch (IIIF manifest, image, or PDF)")
    run.add_argument("-i", "--input", action="append", help="Local PDF or image path")
    run.add_argument("--limit", type=int, default=None, help="Max assets when using --url")
    run.add_argument(
        "--mode",
        choices=["auto", "manuscript", "print"],
        default="auto",
        help="Route pages to transcription-shell or print OCR",
    )
    run.add_argument(
        "--prompt",
        help="Transcription-protocol prompt YAML (required for manuscript mode)",
    )
    run.add_argument(
        "--print-doc-type",
        default=None,
        help="Diachronic print profile (auto picks by year, 1500–present)",
    )
    run.add_argument(
        "--publication-year",
        type=int,
        default=None,
        help="Publication year for auto print doc_type (also inferred from filenames)",
    )
    run.add_argument(
        "--print-language",
        default=None,
        choices=["auto", "en", "la", "de", "fr", "it", "es"],
        help="Orthogonal language axis (combines with year for auto doc_type)",
    )
    run.add_argument(
        "--ocr-combination",
        default=None,
        choices=[
            "default",
            "tesseract_only",
            "tesseract_then_clean",
            "pdf_text_first",
            "shell_print",
        ],
        help="Print OCR fork (mirrors transcription-shell htr_combination)",
    )
    run.add_argument(
        "--fingerprint",
        action="store_true",
        help="Run manuscript-fingerprint scan on PDF sources",
    )
    run.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After print OCR, run Ted Underwood rules via ocr-cleanup (default on)",
    )
    run.add_argument(
        "--extract-figures",
        action="store_true",
        help=(
            "After manuscript transcription, detect embedded images (DocLayNet), "
            "save crops, and insert [fig:id] protocol markers into YAML"
        ),
    )
    run.add_argument(
        "--fast",
        action="store_true",
        help=(
            "Speed-first: smaller images, text-only Tesseract (no layout scan), "
            "skip Underwood clean + internal per-page exports + TEI facsimile"
        ),
    )
    run.add_argument(
        "--symbol-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Drop low-confidence symbol junk and blacklist column rules (|_) "
            "in Tesseract (default on)"
        ),
    )
    run.add_argument(
        "--glyph-heatmap",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Write {basename}.review.png + .review.json beside production TXT "
            "when glyph filtering drops marks (default on; off in --fast)"
        ),
    )
    run.set_defaults(func=cmd_run)

    gui = sub.add_parser("gui", help="Open desktop GUI")
    gui.set_defaults(func=cmd_gui)

    ptypes = sub.add_parser("print-types", help="List diachronic print document types")
    ptypes.set_defaults(func=cmd_print_types)

    bib = sub.add_parser("bib-ocr", help="Extract PDF bibliography citations (bib-ocr package)")
    bib.add_argument("pdf", help="Input PDF")
    bib.add_argument("--max-stage", type=int, default=5, choices=range(1, 6))
    bib.add_argument("-v", "--verbose", action="store_true")
    bib.add_argument("--json", action="store_true", help="Emit full JSON result")
    bib.set_defaults(func=cmd_bib_ocr)

    tess = sub.add_parser("tesseract", help="Show Tesseract binary, version, and language packs")
    tess.add_argument("-v", "--verbose", action="store_true", help="List all installed langs")
    tess.add_argument("--lang", help="Check a lang bundle (e.g. lat+frk+eng)")
    tess.set_defaults(func=cmd_tesseract)

    conv = sub.add_parser(
        "convert-images",
        help="Convert TIF/BMP/WebP/etc. to JPEG/PNG with optional PAGE-XML scaling",
    )
    conv.add_argument("input", nargs="+", help="Image files or directories")
    conv.add_argument("--out-dir")
    conv.add_argument("--format", choices=["jpeg", "png"], default="jpeg")
    conv.add_argument("--max-width", type=int, default=3000)
    conv.add_argument("--max-height", type=int, default=None)
    conv.add_argument("--max-pixels", type=int, default=16_000_000)
    conv.add_argument("--quality", type=int, default=90)
    conv.add_argument("--keep-original", action="store_true")
    conv.add_argument("--recurse", action="store_true")
    conv.add_argument("--force", action="store_true")
    conv.add_argument("--dry-run", action="store_true")
    conv.add_argument("--no-scale-xml", action="store_true")
    conv.add_argument(
        "--use-cucim",
        action="store_true",
        help="GPU resize via cuCIM when installed (falls back to Pillow)",
    )
    conv.set_defaults(func=cmd_convert_images)

    eco = sub.add_parser("ecosystem", help="Print catalog of related GitHub tools")
    eco.set_defaults(func=cmd_ecosystem)

    acq = sub.add_parser("acquire", help="Fetch or copy sources only")
    acq.add_argument("job_id")
    acq.add_argument("--url")
    acq.add_argument("-i", "--input", action="append")
    acq.add_argument("--limit", type=int, default=None)
    acq.set_defaults(func=cmd_acquire)

    exp = sub.add_parser("export", help="Rebuild corpus exports from manifest")
    exp.add_argument("job_id")
    exp.set_defaults(func=cmd_export)

    st = sub.add_parser("status", help="Show job manifest")
    st.add_argument("job_id")
    st.set_defaults(func=cmd_status)

    tools = sub.add_parser("tools", help="Check optional external CLIs on PATH")
    tools.set_defaults(func=cmd_tools)

    cnn = sub.add_parser("cnn", help="Page material classifier (print vs manuscript)")
    cnn_sub = cnn.add_subparsers(dest="cnn_command", required=True)

    cnn_train = cnn_sub.add_parser("train", help="Train ResNet page classifier")
    cnn_train.add_argument("--data", default="data/page_cnn")
    cnn_train.add_argument("--out", default="models/page_cnn.pt")
    cnn_train.add_argument("--epochs", type=int, default=15)
    cnn_train.add_argument("--batch-size", type=int, default=16)
    cnn_train.add_argument("--lr", type=float, default=1e-3)
    cnn_train.add_argument("--image-size", type=int, default=224)
    cnn_train.add_argument(
        "--patience",
        type=int,
        default=3,
        help="Stop when val accuracy fails to improve for N epochs (0 = run all epochs)",
    )
    cnn_train.add_argument(
        "--extra-data",
        action="append",
        metavar="DIR",
        help="Extra dataset roots with print/ and manuscript/ subfolders",
    )
    cnn_train.set_defaults(func=cmd_cnn_train)

    cnn_src = cnn_sub.add_parser("sources", help="List page-CNN training data sources")
    cnn_src.set_defaults(func=cmd_cnn_sources)

    cnn_fetch = cnn_sub.add_parser("fetch", help="Download HF / harvest OCRDatasets / Akdeniz GT")
    cnn_fetch.add_argument("--out", default="data/page_cnn")
    cnn_fetch.add_argument("--source", action="append", help="HF source id from cnn sources")
    cnn_fetch.add_argument("--ocrdatasets", action="append", help="OCRDatasets catalog id")
    cnn_fetch.add_argument("--akdeniz-gt", action="append", help="Akdeniz remote_gt id")
    cnn_fetch.add_argument("--ocrdatasets-root", help="Path to OCRDatasets checkout or data parent")
    cnn_fetch.add_argument("--akdeniz-home", help="Akdeniz $HOME for --akdeniz-gt harvest")
    cnn_fetch.add_argument(
        "--extra",
        action="append",
        metavar="LABEL:PATH",
        help="Copy local images: print:/path or manuscript:/path",
    )
    cnn_fetch.add_argument("--limit", type=int, default=None)
    cnn_fetch.add_argument("--all-hf", action="store_true", help="Fetch all HF sources in registry")
    cnn_fetch.set_defaults(func=cmd_cnn_fetch)

    cnn_pred = cnn_sub.add_parser("predict", help="Classify page image(s)")
    cnn_pred.add_argument("image", nargs="+")
    cnn_pred.set_defaults(func=cmd_cnn_predict)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
