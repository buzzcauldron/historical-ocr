"""historical-ocr command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from historical_ocr import __version__
from historical_ocr.config import Settings
from historical_ocr.backends import bib_ocr as bib_backend
from historical_ocr.backends import ocr_cleanup as underwood_backend
from historical_ocr.backends import tesseract as tess_backend
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
        quality=args.quality,
        clean=args.clean,
        print_doc_type=args.print_doc_type,
        ocr_combination=args.ocr_combination,
        publication_year=args.publication_year,
        print_language=args.print_language,
        fast=args.fast,
        rules_only=args.rules_only,
        low_latency=args.low_latency,
        symbol_filter=args.symbol_filter,
        glyph_heatmap=args.glyph_heatmap,
        review_conf_threshold=args.review_conf_threshold,
        fingerprint=args.fingerprint,
        extract_figures=args.extract_figures,
        deskew=args.deskew,
        overlaid_ocr=args.overlaid_ocr,
        text_slice_only=args.text_slice_only,
        text_slice_include_ads=args.include_ads,
        text_slice_include_figures=args.include_figures,
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
    tools = {
        "tesseract (print OCR)": tess_backend.available(),
        "bib-ocr (PDF bibliography cascade)": bib_backend.available(),
        "ocr-cleanup / Underwood rules (print clean)": underwood_backend.available(),
    }
    for name, ok in tools.items():
        print(f"{'✓' if ok else '✗'} {name}")
    if tess_backend.available():
        print(f"  → {tess_backend.describe(lang_bundle=settings.tesseract_lang)}")
        missing = tess_backend.historical_langs_missing()
        if missing:
            print(f"  → recommended packs not installed: {', '.join(missing)}")
    print(f"  → {bib_backend.describe()}")
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

    newspaper_gt_dir = (
        Path(args.newspaper_gt).expanduser().resolve() if getattr(args, "newspaper_gt", None) else None
    )
    newspaper_sources = getattr(args, "newspaper_source", None)
    if newspaper_gt_dir and not newspaper_sources:
        newspaper_sources = ["chronicling-america"]

    counts = fetch_sources(
        out,
        hf_sources=args.source,
        ocrdatasets_sources=args.ocrdatasets,
        newspaper_gt_sources=newspaper_sources,
        newspaper_gt_dir=newspaper_gt_dir,
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


def cmd_gt_eval(args: argparse.Namespace) -> int:
    from historical_ocr.ml.gt_eval import eval_newspaper_gt

    report = eval_newspaper_gt(
        Path(args.gt_dir).expanduser().resolve(),
        split=args.split,
        limit=args.limit,
        out_dir=Path(args.out).expanduser().resolve() if args.out else None,
        preset=args.preset,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(
        {
            "preset": report.get("preset"),
            "scored": report["scored"],
            "mean_cer": report["mean_cer"],
            "mean_wer": report["mean_wer"],
            "by_doc_type": report.get("by_doc_type"),
        },
        indent=2,
    ))
    return 0 if report["scored"] else 1


def cmd_gt_validate(args: argparse.Namespace) -> int:
    from historical_ocr.ml.gt_eval import validate_newspaper_accuracy

    summary = validate_newspaper_accuracy(
        Path(args.gt_dir).expanduser().resolve(),
        split=args.split,
        limit=args.limit,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(summary, indent=2))
    return 0 if any(p.get("scored") for p in summary.get("presets", {}).values()) else 1


def cmd_gt_submit(args: argparse.Namespace) -> int:
    from historical_ocr.ml.user_corrections import submit_correction, submit_from_job

    corpus = Path(args.corpus).expanduser().resolve()
    if args.job:
        settings = Settings()
        saved = submit_from_job(
            args.job,
            jobs_dir=settings.jobs_dir,
            corpus=corpus,
            corrected_path=Path(args.corrected).expanduser().resolve() if args.corrected else None,
            split=args.split,
            log_fn=lambda m: print(m, file=sys.stderr),
        )
        print(json.dumps({"submitted": len(saved), "corpus": str(corpus)}, indent=2))
        return 0

    if not args.image or not args.corrected or not args.raw:
        print("error: provide --job JOB or (--image, --raw, --corrected)", file=sys.stderr)
        return 1
    dest = submit_correction(
        corpus,
        record_id=args.id or Path(args.image).stem,
        image_src=Path(args.image).expanduser().resolve(),
        raw_text=Path(args.raw).read_text(encoding="utf-8"),
        corrected_text=Path(args.corrected).read_text(encoding="utf-8"),
        split=args.split,
        meta={"source": "cli"},
    )
    print(json.dumps({"submitted": 1, "text": str(dest), "corpus": str(corpus)}, indent=2))
    return 0


def cmd_gt_tune(args: argparse.Namespace) -> int:
    from historical_ocr.ml.user_corrections import tune_corpus

    stats = tune_corpus(
        Path(args.corpus).expanduser().resolve(),
        min_count=args.min_count,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(stats, indent=2))
    return 0 if stats["rules"] else 1


def cmd_gt_template(args: argparse.Namespace) -> int:
    """Copy production export .txt to .corrected.txt for human editing."""
    from historical_ocr.lib.export_names import production_paths, resolve_export_basename
    from historical_ocr.models.manifest import JobManifest

    settings = Settings()
    job_root = (settings.jobs_dir / args.job).expanduser().resolve()
    manifest = JobManifest.model_validate_json((job_root / "manifest.json").read_text(encoding="utf-8"))
    basename = resolve_export_basename(manifest)
    paths = production_paths(job_root / "export", basename)
    src = paths["txt"]
    if not src.is_file():
        print(f"error: missing export text {src}", file=sys.stderr)
        return 1
    dest = src.with_name(f"{basename}.corrected.txt")
    if dest.is_file() and not args.force:
        print(str(dest))
        return 0
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(str(dest))
    return 0


def cmd_newspaper_prepare(args: argparse.Namespace) -> int:
    from historical_ocr.ml.newspaper_train import CorpusSource, prepare_training_corpus

    sources = [
        CorpusSource("chronicling_america", Path(args.ca), "ca"),
        CorpusSource("user_corrections", Path(args.user), "user"),
    ]
    for item in args.extra or []:
        name, _, path = item.partition(":")
        if not name or not path:
            print(f"error: bad --extra {item!r}", file=sys.stderr)
            return 1
        sources.append(CorpusSource(name, Path(path), name.replace("/", "_")[:12]))

    manifest = prepare_training_corpus(
        Path(args.out).expanduser().resolve(),
        sources=sources,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(manifest["counts"], indent=2))
    return 0 if manifest["counts"]["train"] else 1


def cmd_newspaper_train(args: argparse.Namespace) -> int:
    from historical_ocr.ml.newspaper_train import train_newspaper_ocr

    meta = train_newspaper_ocr(
        Path(args.data).expanduser().resolve(),
        Path(args.out).expanduser().resolve(),
        patience=args.patience,
        eval_limit=args.eval_limit,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(meta, indent=2))
    return 0


def cmd_newspaper_eval(args: argparse.Namespace) -> int:
    args.gt_dir = args.data
    return cmd_gt_eval(args)


def cmd_tess_sources(_args: argparse.Namespace) -> int:
    from historical_ocr.ml.tesseract_train import list_sources

    for spec in list_sources():
        print(
            f"{spec.source_id:28}  {spec.kind:20}  "
            f"limit={spec.default_limit:5}  {spec.print_doc_type or '—':22}  "
            f"{spec.notes}",
        )
    return 0


def cmd_tess_fetch(args: argparse.Namespace) -> int:
    from historical_ocr.ml.tesseract_train import fetch_sources

    hf = args.source if args.source else None
    local = args.local if args.local else None
    inst_filters: dict | None = None
    if any(
        getattr(args, k, None) is not None
        for k in ("min_ocr_score", "min_year", "max_year", "language")
    ):
        inst_filters = {}
        if args.min_ocr_score is not None:
            inst_filters["min_ocr_score"] = args.min_ocr_score
        if args.min_year is not None:
            inst_filters["min_year"] = args.min_year
        if args.max_year is not None:
            inst_filters["max_year"] = args.max_year
        if args.language is not None:
            inst_filters["language_gen"] = args.language
    counts = fetch_sources(
        Path(args.out).expanduser().resolve(),
        hf_sources=hf,
        local_sources=local,
        limit=args.limit,
        institutional_filters=inst_filters,
        archive_org=getattr(args, "archive_org", False),
        max_pages_per_volume=getattr(args, "max_pages", 30),
        hf_page_text=not getattr(args, "no_hf_text", False),
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps({"out": args.out, "counts": counts}, indent=2))
    return 0 if any(counts.values()) else 1


def cmd_tess_prepare(args: argparse.Namespace) -> int:
    from historical_ocr.ml.tesseract_train import prepare_tesstrain_ground_truth

    stats = prepare_tesstrain_ground_truth(
        Path(args.corpus).expanduser().resolve(),
        Path(args.corpus).expanduser().resolve(),
        model_name=args.model,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(stats, indent=2))
    return 0 if stats.get("line_pairs", 0) >= 100 else 1


def cmd_tess_train(args: argparse.Namespace) -> int:
    from historical_ocr.ml.tesseract_train import train_tesseract_model

    stats = train_tesseract_model(
        Path(args.data).expanduser().resolve(),
        Path(args.out).expanduser().resolve(),
        model_name=args.model,
        max_iterations=args.max_iterations,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(stats, indent=2))
    return 0 if not stats.get("skipped") else 1


def cmd_tess_train_gt(args: argparse.Namespace) -> int:
    """Fine-tune from an external flat ground-truth/ dir (e.g. transcription-shell pre1800)."""
    from historical_ocr.ml.tesseract_train import load_registry, train_from_ground_truth_dir

    reg = load_registry()
    pre1800 = reg.get("pre1800") or {}
    model = args.model or str(pre1800.get("model_name", "lat_pre1800"))
    start = args.start_model or str(pre1800.get("start_model", "Fraktur"))
    iters = args.max_iterations or int(pre1800.get("max_iterations", 100_000))
    ratio = args.ratio_train if args.ratio_train is not None else float(pre1800.get("ratio_train", 0.99))

    stats = train_from_ground_truth_dir(
        Path(args.ground_truth).expanduser().resolve(),
        Path(args.out).expanduser().resolve(),
        model_name=model,
        start_model=start,
        max_iterations=iters,
        ratio_train=ratio,
        tesstrain_root=Path(args.tesstrain).expanduser().resolve() if args.tesstrain else None,
        tessdata_dir=Path(args.tessdata).expanduser().resolve() if args.tessdata else None,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(json.dumps(stats, indent=2))
    return 0 if not stats.get("skipped") else 1


def cmd_gt_fetch(args: argparse.Namespace) -> int:
    from historical_ocr.ml.newspaper_gt import CHRONAM_REPO, fetch_newspaper_gt

    shards = None
    if args.shard is not None:
        if not 0 <= args.shard <= 3:
            print("error: --shard must be 0-3", file=sys.stderr)
            return 1
        shards = [f"data/train-{args.shard:05d}-of-00004.parquet"]

    print(f"source: {CHRONAM_REPO}", file=sys.stderr)
    stats = fetch_newspaper_gt(
        Path(args.out).expanduser().resolve(),
        limit=args.limit,
        val_ratio=args.val_ratio,
        seed=args.seed,
        skip_images=args.text_only,
        shards=shards,
        log_fn=lambda m: print(m, file=sys.stderr),
    )
    print(
        f"saved {stats['saved']} ({stats['train']} train, {stats['val']} val); "
        f"on disk: {stats['total_train']} train, {stats['total_val']} val",
    )
    return 0


def cmd_cnn_predict(args: argparse.Namespace) -> int:
    from historical_ocr.backends import page_cnn as cnn_backend

    model_path = Path(args.model).expanduser().resolve()
    if not cnn_backend.available(model_path):
        print(f"error: CNN model not found: {model_path}", file=sys.stderr)
        return 1
    for image in args.image:
        path = Path(image).expanduser().resolve()
        label, score = cnn_backend.classify_page(
            path,
            model_path=model_path,
            threshold=args.threshold,
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
        description="Produce computational-ready text from historical newspapers and print.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Full pipeline for a job")
    run.add_argument("job_id", help="Job identifier (creates jobs/<job_id>/)")
    run.add_argument("--url", help="Repository URL to fetch (IIIF manifest, image, or PDF)")
    run.add_argument("-i", "--input", action="append", help="Local PDF or image path")
    run.add_argument("--limit", type=int, default=None, help="Max assets when using --url")
    run.add_argument(
        "--quality",
        choices=["free", "medium", "high"],
        default=None,
        help="Quality tier (default medium — glyph filter + tune rules; overrides when no --fast/--low-latency)",
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
        ],
        help="Print OCR pipeline variant",
    )
    run.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After print OCR, run Ted Underwood rules via ocr-cleanup (default on)",
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
        "--rules-only",
        action="store_true",
        help=(
            "LLM-independent print path: Tesseract + glyph/symbol filter + "
            "Underwood rules (ignores HISTORICAL_OCR_CLEAN_LLM)"
        ),
    )
    run.add_argument(
        "--low-latency",
        action="store_true",
        help=(
            "Speed-first rules-only: text-only Tesseract, Underwood clean, "
            "orphan-line drop; skips glyph crops and review PNG (recommended for batches)"
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
            "Write {basename}.review.png + .review.json for problem pages only "
            "(glyph drops or lines below --review-conf-threshold; default on)"
        ),
    )
    run.add_argument(
        "--review-conf-threshold",
        type=float,
        default=None,
        metavar="CONF",
        help="Emit review PNG when any OCR line confidence is below CONF (default 65)",
    )
    run.add_argument(
        "--fingerprint",
        action="store_true",
        help="Run manuscript-fingerprint type-case scan on PDF sources (routing hint)",
    )
    run.add_argument(
        "--extract-figures",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Detect illustrations/tables and write [fig:id] markers (default on for medium/high)",
    )
    run.add_argument(
        "--deskew",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Straighten page rotation before OCR (default on for medium/high)",
    )
    run.add_argument(
        "--text-slice-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="OCR only prose/list sections from ink layout; skip ads/illustrations by default",
    )
    run.add_argument(
        "--include-ads",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="When text slicing, also keep advertisement/header-like regions",
    )
    run.add_argument(
        "--include-figures",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="When text slicing, also keep illustration/photo regions",
    )
    run.add_argument(
        "--overlaid-ocr",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="OCR ink-zone overlays from heatmap columns/sections (default on for medium/high)",
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
    cnn_fetch.add_argument(
        "--newspaper-gt",
        help="Corpus from gt fetch (e.g. data/newspaper_gt); harvests chronicling-america by default",
    )
    cnn_fetch.add_argument(
        "--newspaper-source",
        action="append",
        help="Newspaper GT registry id (default chronicling-america when --newspaper-gt set)",
    )
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

    cnn_pred = cnn_sub.add_parser("predict", help="Classify page image(s) (legacy print/manuscript CNN)")
    cnn_pred.add_argument("image", nargs="+")
    cnn_pred.add_argument("--model", default="models/page_cnn.pt")
    cnn_pred.add_argument("--threshold", type=float, default=0.5)
    cnn_pred.set_defaults(func=cmd_cnn_predict)

    gt = sub.add_parser("gt", help="Newspaper OCR ground-truth corpora")
    gt_sub = gt.add_subparsers(dest="gt_command", required=True)

    gt_tpl = gt_sub.add_parser(
        "template",
        help="Copy export .txt → .corrected.txt for human editing",
    )
    gt_tpl.add_argument("job", help="Job id (jobs/<job>/)")
    gt_tpl.add_argument("--force", action="store_true", help="Overwrite existing .corrected.txt")
    gt_tpl.set_defaults(func=cmd_gt_template)

    gt_submit = gt_sub.add_parser(
        "submit",
        help="Import human-corrected text into data/user_gt tuning corpus",
    )
    gt_submit.add_argument("--corpus", default="data/user_gt")
    gt_submit.add_argument("--job", help="Job id — reads export/*.corrected.txt or --corrected")
    gt_submit.add_argument("--corrected", help="Path to corrected text file")
    gt_submit.add_argument("--image", help="Page image (standalone submit)")
    gt_submit.add_argument("--raw", help="Raw OCR text file (standalone submit)")
    gt_submit.add_argument("--id", help="Record id for standalone submit")
    gt_submit.add_argument("--split", choices=["train", "val"], default="train")
    gt_submit.set_defaults(func=cmd_gt_submit)

    gt_tune = gt_sub.add_parser(
        "tune",
        help="Mine replacement rules from submitted corrections → tuned_rules.json",
    )
    gt_tune.add_argument("--corpus", default="data/user_gt")
    gt_tune.add_argument("--min-count", type=int, default=1)
    gt_tune.set_defaults(func=cmd_gt_tune)

    gt_fetch = gt_sub.add_parser(
        "fetch",
        help="Download Chronicling America pages + OCR text (train/val split)",
    )
    gt_fetch.add_argument("--out", default="data/newspaper_gt")
    gt_fetch.add_argument("--limit", type=int, default=500)
    gt_fetch.add_argument("--val-ratio", type=float, default=0.1)
    gt_fetch.add_argument("--seed", type=int, default=42)
    gt_fetch.add_argument(
        "--text-only",
        action="store_true",
        help="Save OCR text + metadata only (skip page images)",
    )
    gt_fetch.add_argument("--shard", type=int, default=None, help="Parquet shard 0-3 only")
    gt_fetch.set_defaults(func=cmd_gt_fetch)

    gt_eval = gt_sub.add_parser(
        "eval",
        help="Rules-only OCR on GT split + CER/WER vs reference text (no LLM)",
    )
    gt_eval.add_argument("--gt-dir", default="data/newspaper_gt")
    gt_eval.add_argument("--split", choices=["train", "val", "all"], default="val")
    gt_eval.add_argument("--limit", type=int, default=None)
    gt_eval.add_argument(
        "--preset",
        choices=["free", "medium"],
        default="medium",
        help="Quality preset to benchmark (default medium = production)",
    )
    gt_eval.add_argument("--out", help="Eval run directory (default: <gt-dir>/eval/<timestamp>)")
    gt_eval.set_defaults(func=cmd_gt_eval)

    gt_validate = gt_sub.add_parser(
        "validate",
        help="Compare free vs medium on GT split and pick best CER",
    )
    gt_validate.add_argument("--gt-dir", default="data/newspaper_gt")
    gt_validate.add_argument("--split", choices=["train", "val", "all"], default="val")
    gt_validate.add_argument("--limit", type=int, default=None)
    gt_validate.set_defaults(func=cmd_gt_validate)

    np = sub.add_parser("newspaper", help="Newspaper OCR training (Kraken + GT corpora)")
    np_sub = np.add_subparsers(dest="newspaper_command", required=True)

    np_prep = np_sub.add_parser("prepare", help="Merge CA GT + user corrections → data/newspaper_ocr")
    np_prep.add_argument("--out", default="data/newspaper_ocr")
    np_prep.add_argument("--ca", default="data/newspaper_gt")
    np_prep.add_argument("--user", default="data/user_gt")
    np_prep.add_argument("--extra", action="append", metavar="NAME:PATH")
    np_prep.set_defaults(func=cmd_newspaper_prepare)

    np_train = np_sub.add_parser("train", help="Train Kraken model (requires ketos on PATH)")
    np_train.add_argument("--data", default="data/newspaper_ocr")
    np_train.add_argument("--out", default="models/newspaper_ocr.mlmodel")
    np_train.add_argument("--epochs", type=int, default=30)
    np_train.add_argument("--batch-size", type=int, default=8)
    np_train.set_defaults(func=cmd_newspaper_train)

    np_eval = np_sub.add_parser("eval", help="Eval rules-only OCR vs prepared val split")
    np_eval.add_argument("--data", default="data/newspaper_ocr")
    np_eval.add_argument("--split", choices=["train", "val", "all"], default="val")
    np_eval.add_argument("--limit", type=int, default=None)
    np_eval.add_argument("--out", help="Eval run directory")
    np_eval.set_defaults(func=cmd_newspaper_eval)

    tess_train = sub.add_parser("tess", help="Tesseract LSTM fine-tuning (HF corpora + tesstrain)")
    tess_sub = tess_train.add_subparsers(dest="tess_command", required=True)

    tess_src = tess_sub.add_parser("sources", help="List HF/local tess train corpora")
    tess_src.set_defaults(func=cmd_tess_sources)

    tess_fetch = tess_sub.add_parser(
        "fetch",
        help="Download HF/local page+text into tess corpus (or metadata catalog for institutional-books)",
    )
    tess_fetch.add_argument("--out", default="data/tesseract_train")
    tess_fetch.add_argument(
        "--source",
        action="append",
        help="HF source id (default: chronicling-america, newspaper-ocr-gold, ocr-quality)",
    )
    tess_fetch.add_argument("--local", action="append", help="Local corpus id (newspaper_gt, user_gt)")
    tess_fetch.add_argument("--limit", type=int, default=None, help="Cap per source")
    tess_fetch.add_argument(
        "--min-ocr-score",
        type=float,
        default=None,
        metavar="N",
        help="institutional-books: min Google + OCRoscope score (default 70)",
    )
    tess_fetch.add_argument(
        "--min-year",
        type=int,
        default=None,
        help="institutional-books: earliest publication year (default 1800)",
    )
    tess_fetch.add_argument(
        "--max-year",
        type=int,
        default=None,
        help="institutional-books: latest publication year (default 1920)",
    )
    tess_fetch.add_argument(
        "--language",
        default=None,
        help="institutional-books: ISO 639-3 language_gen filter (default eng)",
    )
    tess_fetch.add_argument(
        "--archive-org",
        action="store_true",
        help=(
            "institutional-books: resolve Internet Archive IIIF scans for catalog "
            "rows and download page JPEGs into tess corpus pages/"
        ),
    )
    tess_fetch.add_argument(
        "--max-pages",
        type=int,
        default=30,
        metavar="N",
        help="Max IA page images per volume when using --archive-org (default 30)",
    )
    tess_fetch.add_argument(
        "--no-hf-text",
        action="store_true",
        help="institutional-books --archive-org: skip HF text_by_page GT (images only)",
    )
    tess_fetch.set_defaults(func=cmd_tess_fetch)

    tess_prep = tess_sub.add_parser("prepare", help="Extract line PNG+.gt.txt for tesstrain")
    tess_prep.add_argument("--corpus", default="data/tesseract_train")
    tess_prep.add_argument("--model", default=None, help="Model name (default histnews)")
    tess_prep.set_defaults(func=cmd_tess_prepare)

    tess_run = tess_sub.add_parser("train", help="Run tesstrain make training")
    tess_run.add_argument("--data", default="data/tesseract_train")
    tess_run.add_argument("--out", default="models/histnews.traineddata")
    tess_run.add_argument("--model", default=None)
    tess_run.add_argument("--max-iterations", type=int, default=None)
    tess_run.set_defaults(func=cmd_tess_train)

    tess_gt = tess_sub.add_parser(
        "train-gt",
        help="Fine-tune from flat ground-truth/*.png + *.gt.txt (transcription-shell pre1800)",
    )
    tess_gt.add_argument("--ground-truth", required=True, help="Directory of line PNG + .gt.txt pairs")
    tess_gt.add_argument("--out", default="models/lat_pre1800.traineddata")
    tess_gt.add_argument("--model", default=None, help="Output lang id (default from pre1800 registry)")
    tess_gt.add_argument("--start-model", default=None, help="Base traineddata stem (default Fraktur)")
    tess_gt.add_argument("--max-iterations", type=int, default=None)
    tess_gt.add_argument("--ratio-train", type=float, default=None)
    tess_gt.add_argument("--tesstrain", default=None, help="Path to tesstrain clone")
    tess_gt.add_argument("--tessdata", default=None, help="Directory with START_MODEL.traineddata")
    tess_gt.set_defaults(func=cmd_tess_train_gt)

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
