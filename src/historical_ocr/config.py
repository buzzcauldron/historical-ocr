"""Settings and job layout for historical-ocr."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_ENV_KEYS = (
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
)


def bootstrap_shared_env() -> None:
    """Use sibling transcription-shell/.env when local keys are unset or empty."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return

    shell_env = _REPO_ROOT.parent / "transcription-shell" / ".env"
    if not shell_env.is_file():
        return

    local_env = _REPO_ROOT / ".env"
    local_vals = dotenv_values(local_env) if local_env.is_file() else {}
    shell_vals = dotenv_values(shell_env)

    for key in _SHARED_ENV_KEYS:
        current = os.environ.get(key) or local_vals.get(key) or ""
        if str(current).strip():
            continue
        value = shell_vals.get(key)
        if value and str(value).strip():
            os.environ[key] = str(value).strip()

    hf = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if hf:
        os.environ.setdefault("HF_TOKEN", hf)
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", hf)


bootstrap_shared_env()

MaterialMode = Literal["print"]
NormalizationMode = Literal["diplomatic", "normalized", "modern"]
OcrCombination = Literal[
    "default",
    "tesseract_only",
    "tesseract_then_clean",
    "pdf_text_first",
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
    default_provider: str = Field(
        default="anthropic",
        validation_alias="HISTORICAL_OCR_DEFAULT_PROVIDER",
    )
    default_model: str | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_MODEL",
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
    overlaid_ocr_enabled: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_OVERLAID_OCR",
    )
    text_slice_only: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_TEXT_SLICE_ONLY",
    )
    text_slice_include_ads: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_TEXT_SLICE_INCLUDE_ADS",
    )
    text_slice_include_figures: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_TEXT_SLICE_INCLUDE_FIGURES",
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
    review_conf_threshold: float = Field(
        default=65.0,
        ge=0.0,
        le=100.0,
        validation_alias="HISTORICAL_OCR_REVIEW_CONF_THRESHOLD",
    )
    symbol_drop_orphan_lines: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_SYMBOL_DROP_ORPHAN_LINES",
    )
    symbol_orphan_line_chars: str = Field(
        default="1lI|_@.`:",
        validation_alias="HISTORICAL_OCR_SYMBOL_ORPHAN_LINE_CHARS",
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
    tune_rules_path: Path | None = Field(
        default=Path("data/user_gt/tuned_rules.json"),
        validation_alias="HISTORICAL_OCR_TUNE_RULES",
    )
    default_quality: str = Field(
        default="medium",
        validation_alias="HISTORICAL_OCR_DEFAULT_QUALITY",
    )
    tesseract_finetune_lang: str | None = Field(
        default="histnews",
        validation_alias="HISTORICAL_OCR_TESSERACT_FINETUNE_LANG",
    )
    tesseract_finetune_path: Path | None = Field(
        default=Path("models/histnews.traineddata"),
        validation_alias="HISTORICAL_OCR_TESSERACT_FINETUNE_PATH",
    )
    escalate_low_confidence: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_ESCALATE_LOW_CONFIDENCE",
    )
    escalate_min_mean_confidence: float = Field(
        default=72.0,
        validation_alias="HISTORICAL_OCR_ESCALATE_MIN_MEAN_CONF",
    )
    escalate_max_low_conf_ratio: float = Field(
        default=0.35,
        validation_alias="HISTORICAL_OCR_ESCALATE_MAX_LOW_CONF_RATIO",
    )
    fingerprint_enabled: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_FINGERPRINT_ENABLED",
    )
    handwriting_detect_enabled: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_HANDWRITING_DETECT",
    )
    handwriting_gemini_enabled: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_HANDWRITING_GEMINI",
    )
    handwriting_gemini_model: str | None = Field(
        default=None,
        validation_alias="HISTORICAL_OCR_HANDWRITING_GEMINI_MODEL",
    )
    handwriting_gemini_max_regions: int = Field(
        default=8,
        ge=1,
        le=40,
        validation_alias="HISTORICAL_OCR_HANDWRITING_GEMINI_MAX",
    )
    handwriting_gemini_conf_threshold: float = Field(
        default=58.0,
        ge=0.0,
        le=100.0,
        validation_alias="HISTORICAL_OCR_HANDWRITING_GEMINI_CONF",
    )
    per_page_type_routing: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_PER_PAGE_TYPE_ROUTING",
    )
    damage_retry_enabled: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_DAMAGE_RETRY_ENABLED",
    )
    damage_retry_conf_threshold: float = Field(
        default=65.0,
        validation_alias="HISTORICAL_OCR_DAMAGE_RETRY_CONF",
    )
    damage_retry_max_lines: int = Field(
        default=40,
        ge=1,
        le=200,
        validation_alias="HISTORICAL_OCR_DAMAGE_RETRY_MAX_LINES",
    )
    damage_llm_enabled: bool = Field(
        default=False,
        validation_alias="HISTORICAL_OCR_DAMAGE_LLM_ENABLED",
    )
    damage_llm_conf_threshold: float = Field(
        default=55.0,
        ge=0.0,
        le=100.0,
        validation_alias="HISTORICAL_OCR_DAMAGE_LLM_CONF",
    )
    damage_llm_max_lines: int = Field(
        default=12,
        ge=0,
        le=80,
        validation_alias="HISTORICAL_OCR_DAMAGE_LLM_MAX_LINES",
    )
    deskew_enabled: bool = Field(
        default=True,
        validation_alias="HISTORICAL_OCR_DESKEW_ENABLED",
    )
    deskew_max_angle: float = Field(
        default=15.0,
        validation_alias="HISTORICAL_OCR_DESKEW_MAX_ANGLE",
    )
    deskew_min_angle: float = Field(
        default=0.25,
        validation_alias="HISTORICAL_OCR_DESKEW_MIN_ANGLE",
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
        default=True,
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
