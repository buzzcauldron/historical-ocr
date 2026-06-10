"""Job manifest schema — tracks provenance and per-page outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

PageRoute = Literal["manuscript", "print", "skipped"]
PageStatus = Literal["pending", "ok", "error", "skipped"]


class SourceRecord(BaseModel):
    kind: Literal["url", "file", "strigil"]
    value: str
    fetched_at: str | None = None


class PageRecord(BaseModel):
    page_id: str
    image_path: str
    route: PageRoute = "manuscript"
    status: PageStatus = "pending"
    transcription_yaml: str | None = None
    transcription_txt: str | None = None
    tei_path: str | None = None
    ocr_text_path: str | None = None
    clean_text_path: str | None = None
    layout_path: str | None = None
    pagexml_path: str | None = None
    print_doc_type: str | None = None
    fingerprint_score: float | None = None
    errors: list[str] = Field(default_factory=list)


class FingerprintSummary(BaseModel):
    job_dir: str | None = None
    type_case_matches: list[dict[str, Any]] = Field(default_factory=list)
    suggested_material: Literal["manuscript", "print", "unknown"] = "unknown"


class JobManifest(BaseModel):
    job_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    export_basename: str | None = Field(
        default=None,
        description="Stem of the submitted source file; names production exports.",
    )
    sources: list[SourceRecord] = Field(default_factory=list)
    material_mode: Literal["auto", "manuscript", "print"] = "auto"
    resolved_material: Literal["manuscript", "print", "mixed"] | None = None
    fingerprint: FingerprintSummary | None = None
    print_doc_type: str | None = None
    print_ocr_combination: str | None = None
    normalization_mode: str | None = None
    publication_year: int | None = None
    print_language: str | None = None
    pages: list[PageRecord] = Field(default_factory=list)
    export: dict[str, str] = Field(default_factory=dict)

    def page_by_id(self, page_id: str) -> PageRecord | None:
        for p in self.pages:
            if p.page_id == page_id:
                return p
        return None
