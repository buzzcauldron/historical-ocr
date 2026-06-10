"""historical-ocr command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from historical_ocr import __version__
from historical_ocr.config import Settings
from historical_ocr.backends import fingerprint as fp_backend
from historical_ocr.backends import ocr_cleanup as underwood_backend
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
        inputs=inputs or None,
        mode=args.mode,
        prompt=Path(args.prompt) if args.prompt else None,
        fingerprint=args.fingerprint,
        clean=args.clean,
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
    tools = {
        "transcriber-shell (manuscript)": shell_backend.available(),
        "manuscript-fingerprint (type case)": fp_backend.available(),
        "ocr-cleanup / Underwood rules (print clean)": underwood_backend.available(),
    }
    for name, ok in tools.items():
        print(f"{'✓' if ok else '✗'} {name}")
    return 0


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
    run.add_argument("--url", help="Repository URL to fetch via strigil")
    run.add_argument("-i", "--input", action="append", help="Local PDF or image path")
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
    run.set_defaults(func=cmd_run)

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
