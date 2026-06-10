"""Shared types for figure-extraction backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FigureResult:
    """One detected figure region on a page."""

    id: str
    bbox: tuple[int, int, int, int]
    label: str
    confidence: float
    crop_path: Path | None = None
    notes: str = ""


@dataclass
class FigureExtractionReport:
    """Aggregate result for one page."""

    figures: list[FigureResult] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_yaml_section(self) -> list[dict]:
        out: list[dict] = []
        for f in self.figures:
            entry: dict = {
                "id": f.id,
                "bbox_page_px": list(f.bbox),
                "label": f.label,
                "detector_confidence": round(f.confidence, 3),
            }
            if f.crop_path is not None:
                entry["crop_path"] = str(f.crop_path)
            if f.notes:
                entry["notes"] = f.notes
            out.append(entry)
        return out
