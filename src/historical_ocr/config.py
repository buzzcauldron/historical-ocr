"""Settings and job layout for historical-ocr."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MaterialMode = Literal["auto", "manuscript", "print"]
LineationBackend = Literal["glyph_machina", "kraken", "mask"]
NormalizationMode = Literal["diplomatic", "normalized", "modern"]
OcrCombination = Literal[
    "default",
    "tesseract_only",
    "tesseract_then_clean",
    "pdf_text_first",
    "shell_print",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    jobs_dir: Path = Field(
        default=Path("jobs"),
        validation_alias="HISTORICAL_OCR_JOBS_DIR",
    )
    pdf_dpi: int = Field(default=300, validation_alias="HISTORICAL_OCR_PDF_DPI")
    jpeg_quality: int = Field(default=90, validation_alias="HISTORICAL_OCR_JPEG_QUALITY")
    max_image_width: int = Field(default=3000, validation_alias="HISTORICAL_OCR_MAX_IMAGE_WIDTH")
    max_image_height: int | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_MAX_IMAGE_HEIGHT",
    )
    max_image_pixels: int = Field(
        default=16_000_000,
        validation_alias="HISTORICAL_OCR_MAX_IMAGE_PIXELS",
    )
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
    tesseract_cmd: str | None = Field(
        default=None,
        validation_alias="TESSERACT_CMD",
    )
    tessdata_prefix: Path | None = Field(
        default=None,
        validation_alias="TESSDATA_PREFIX",
    )
    bib_preprocess: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_BIB_PREPROCESS",
    )
    pdf_density_ocr: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_PDF_DENSITY_OCR",
    )
    fast_mode: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_FAST_MODE",
    )
    save_layout_artifacts: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_SAVE_LAYOUT_ARTIFACTS",
    )
    export_internal: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_EXPORT_INTERNAL",
    )
    tei_facsimile: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_TEI_FACSIMILE",
    )
    parallel_pages: int = Field(
        default=1,
        ge=1,
        le=16,
        validation_alias="HISTORICAL_OCR_PARALLEL_PAGES",
    )
    jpeg_optimize: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_JPEG_OPTIMIZE",
    )
    symbol_filter: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_SYMBOL_FILTER",
    )
    ocr_min_confidence: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        validation_alias="HISTORICAL_OCR_OCR_MIN_CONFIDENCE",
    )
    tesseract_char_blacklist: str | None = Field(
        default="|_",
        validation_alias="HISTORICAL_OCR_TESSERACT_CHAR_BLACKLIST",
    )
    tesseract_char_whitelist: str | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_TESSERACT_CHAR_WHITELIST",
    )
    symbol_strip_trailing: str = Field(
        default="|_:",
        validation_alias="HISTORICAL_OCR_SYMBOL_STRIP_TRAILING",
    )
    symbol_glyph_filter: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_SYMBOL_GLYPH_FILTER",
    )
    symbol_glyph_heatmap: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_SYMBOL_GLYPH_HEATMAP",
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

    page_cnn_model: Path | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_PAGE_CNN_MODEL",
    )
    page_cnn_threshold: float = Field(
        default=0.5,
        validation_alias="HISTORICAL_OCR_PAGE_CNN_THRESHOLD",
    )

    print_doc_type: str = Field(
        default="auto",
        validation_alias="HISTORICAL_OCR_PRINT_DOC_TYPE",
    )
    publication_year: int | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_PUBLICATION_YEAR",
    )
    print_language: str = Field(
        default="auto",
        validation_alias="HISTORICAL_OCR_PRINT_LANGUAGE",
    )
    ocr_combination: str = Field(
        default="tesseract_then_clean",
        validation_alias="HISTORICAL_OCR_OCR_COMBINATION",
    )
    normalization_mode: NormalizationMode = Field(
        default="normalized",
        validation_alias="HISTORICAL_OCR_NORMALIZATION_MODE",
    )
    print_types_dir: Path | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_PRINT_TYPES_DIR",
    )

    figure_extract_enabled: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_FIGURE_EXTRACT_ENABLED",
    )
    figure_extract_backend: str = Field(
        default="doclaynet",
        validation_alias="HISTORICAL_OCR_FIGURE_EXTRACT_BACKEND",
    )
    figure_extract_model: str = Field(
        default="juliozhao/DocLayout-YOLO-DocLayNet",
        validation_alias="HISTORICAL_OCR_FIGURE_EXTRACT_MODEL",
    )
    figure_min_confidence: float = Field(
        default=0.4,
        validation_alias="HISTORICAL_OCR_FIGURE_MIN_CONFIDENCE",
    )
    figure_min_area_frac: float = Field(
        default=0.01,
        validation_alias="HISTORICAL_OCR_FIGURE_MIN_AREA_FRAC",
    )
    figure_pad_px: int = Field(
        default=8,
        validation_alias="HISTORICAL_OCR_FIGURE_PAD_PX",
    )
    figure_classes: str = Field(
        default="Picture,Table",
        validation_alias="HISTORICAL_OCR_FIGURE_CLASSES",
    )
    figure_device: str = Field(
        default="cpu",
        validation_alias="HISTORICAL_OCR_FIGURE_DEVICE",
    )

    @property
    def figure_classes_list(self) -> list[str]:
        return [x.strip() for x in self.figure_classes.split(",") if x.strip()]


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
