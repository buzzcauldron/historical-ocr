"""Pipeline module scaffold (transcription-shell pattern).

Stages are extracted incrementally from print_route / run_job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from historical_ocr.config import JobPaths, Settings
from historical_ocr.document_types.print_types import PrintDocumentTypeSpec
from historical_ocr.models.manifest import JobManifest, PageRecord


@dataclass
class PipelineContext:
    job: JobPaths
    manifest: JobManifest
    settings: Settings
    print_spec: PrintDocumentTypeSpec | None = None
    source_pdf: Path | None = None
    log: list[str] = field(default_factory=list)

    def log_fn(self, msg: str) -> None:
        self.log.append(msg)


class PipelineModule(Protocol):
    name: str

    def applies(self, ctx: PipelineContext, page: PageRecord) -> bool: ...

    def run(self, ctx: PipelineContext, page: PageRecord) -> None: ...


class PrintOcrModule:
    name = "print_ocr"

    def applies(self, ctx: PipelineContext, page: PageRecord) -> bool:
        return page.route == "print"

    def run(self, ctx: PipelineContext, page: PageRecord) -> None:
        from historical_ocr.pipeline.print_route import ocr_single_page

        ocr_single_page(
            page,
            ctx.job,
            ctx.settings,
            print_spec=ctx.print_spec,
            source_pdf=ctx.source_pdf,
            log_fn=ctx.log_fn,
        )


DEFAULT_PRINT_MODULES: list[PipelineModule] = [PrintOcrModule()]
