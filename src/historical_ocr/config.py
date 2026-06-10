"""Settings and job layout for historical-ocr."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MaterialMode = Literal["auto", "manuscript", "print"]
LineationBackend = Literal["glyph_machina", "kraken", "mask"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jobs_dir: Path = Field(
        default=Path("jobs"),
        validation_alias="HISTORICAL_OCR_JOBS_DIR",
    )
    pdf_dpi: int = Field(default=300, validation_alias="HISTORICAL_OCR_PDF_DPI")
    fingerprint_dpi: int = Field(default=800, validation_alias="HISTORICAL_OCR_FINGERPRINT_DPI")
    fingerprint_seg_dpi: int = Field(
        default=300,
        validation_alias="HISTORICAL_OCR_FINGERPRINT_SEG_DPI",
    )

    default_provider: str = Field(
        default="anthropic",
        validation_alias="HISTORICAL_OCR_DEFAULT_PROVIDER",
    )
    default_model: str | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_MODEL",
    )
    lineation_backend: LineationBackend = Field(
        default="glyph_machina",
        validation_alias="HISTORICAL_OCR_LINEATION_BACKEND",
    )
    tesseract_lang: str = Field(
        default="lat+frk+eng",
        validation_alias="HISTORICAL_OCR_TESSERACT_LANG",
    )

    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")

    clean_print: bool = Field(default=True, validation_alias="HISTORICAL_OCR_CLEAN_PRINT")
    clean_apply_variants: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_CLEAN_VARIANTS",
    )
    clean_rejoin_linebreaks: bool = Field(default=True)
    clean_apply_corrections: bool = Field(default=True)
    clean_llm: str | None = Field(default=None, validation_alias="HISTORICAL_OCR_CLEAN_LLM")
    clean_llm_model: str | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_CLEAN_LLM_MODEL",
    )


class JobPaths:
    """Canonical layout for a single historical-ocr job."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.source = self.root / "source"
        self.pages = self.root / "pages"
        self.artifacts = self.root / "artifacts"
        self.fingerprint = self.root / "fingerprint"
        self.ocr = self.root / "ocr"
        self.clean = self.root / "clean"
        self.export = self.root / "export"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    def ensure(self) -> None:
        for d in (
            self.source,
            self.pages,
            self.artifacts,
            self.fingerprint,
            self.ocr,
            self.clean,
            self.export,
            self.export / "tei",
        ):
            d.mkdir(parents=True, exist_ok=True)
