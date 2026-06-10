"""Manuscript transcription via external transcriber-shell."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from historical_ocr.backends import transcriber_shell as shell
from historical_ocr.config import JobPaths, Settings
from historical_ocr.lib.protocol_text import plain_text_from_yaml_dict
from historical_ocr.lib.tei_minimal import yaml_to_tei
from historical_ocr.models.manifest import JobManifest, PageRecord


def transcribe_pages(
    pages: list[PageRecord],
    job: JobPaths,
    manifest: JobManifest,
    settings: Settings,
    *,
    prompt_path: Path,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    prompt_path = prompt_path.expanduser().resolve()
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    for page in pages:
        if page.route != "manuscript":
            continue

        image = (job.root / page.image_path).resolve()
        _log(f"transcribe: {page.page_id}")

        proc = shell.run_page(
            job_id=page.page_id,
            image=image,
            prompt=prompt_path,
            provider=settings.default_provider,
            model=settings.default_model,
            lineation=settings.lineation_backend,
            artifacts_dir=job.artifacts,
        )
        if proc.returncode != 0:
            page.status = "error"
            err = (proc.stderr or proc.stdout or "transcriber-shell failed").strip()
            page.errors.append(err[:500])
            continue

        yaml_path = shell.find_transcription_yaml(job.artifacts, page.page_id, image)
        if not yaml_path or not yaml_path.is_file():
            page.status = "error"
            page.errors.append("transcription YAML not found after run")
            continue

        page.transcription_yaml = str(yaml_path.relative_to(job.root))
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        txt_path = job.artifacts / page.page_id / f"{image.stem}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            plain = plain_text_from_yaml_dict(data)
            txt_path.write_text(plain + "\n", encoding="utf-8")
            page.transcription_txt = str(txt_path.relative_to(job.root))

        tei_out = job.export / "tei" / f"{page.page_id}.xml"
        yaml_to_tei(yaml_path, tei_out)
        page.tei_path = str(tei_out.relative_to(job.root))
        page.status = "ok"
