"""Ted Underwood OCRnormalizer — via sibling ``ocr-cleanup`` package.

``ocr-cleanup`` (fork of tedunderwood/DataMunging) ships the lexicographic
rulesets and a non-interactive ``apply_rules`` / ``CleanupPipeline`` API.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _sibling_repo() -> Path | None:
    here = Path(__file__).resolve()
    candidate = here.parents[4] / "ocr-cleanup"
    if candidate.is_dir() and (candidate / "rulesets").is_dir():
        return candidate
    return None


def _ensure_importable() -> bool:
    try:
        import ocr_cleanup  # noqa: F401

        return True
    except ImportError:
        sibling = _sibling_repo()
        if sibling and str(sibling / "src") not in sys.path:
            sys.path.insert(0, str(sibling / "src"))
        try:
            import ocr_cleanup  # noqa: F401

            return True
        except ImportError:
            return False


def available() -> bool:
    return _ensure_importable() or shutil.which("ocr-cleanup") is not None


def _cleaner_kwargs(
    llm: str,
    *,
    model: str | None,
    anthropic_api_key: str | None,
    google_api_key: str | None,
    openai_api_key: str | None,
) -> dict:
    kw: dict = {}
    if model:
        kw["model"] = model
    provider = llm.lower()
    if provider == "gemini" and google_api_key:
        kw["api_key"] = google_api_key
    elif provider == "anthropic" and anthropic_api_key:
        kw["api_key"] = anthropic_api_key
    elif provider == "openai" and openai_api_key:
        kw["api_key"] = openai_api_key
    return kw


def clean_text(
    text: str,
    *,
    apply_variants: bool = False,
    rejoin_linebreaks: bool = True,
    apply_corrections: bool = True,
    llm: str | None = None,
    model: str | None = None,
    anthropic_api_key: str | None = None,
    google_api_key: str | None = None,
    openai_api_key: str | None = None,
) -> str:
    """Rule-based (and optional LLM) cleanup for English print OCR."""
    if _ensure_importable():
        from ocr_cleanup.pipeline import CleanupPipeline
        from ocr_cleanup.rules import RuleSet
        from ocr_cleanup.providers import get_cleaner

        sibling = _sibling_repo()
        rules_dir = (sibling / "rulesets") if sibling else None
        rs = RuleSet.load(rules_dir)

        cleaner = None
        if llm and llm != "none":
            kw = _cleaner_kwargs(
                llm,
                model=model,
                anthropic_api_key=anthropic_api_key,
                google_api_key=google_api_key,
                openai_api_key=openai_api_key,
            )
            cleaner = get_cleaner(llm, **kw)

        result = CleanupPipeline(
            rules=rs,
            cleaner=cleaner,
            apply_variants=apply_variants,
            rejoin_linebreaks=rejoin_linebreaks,
            apply_corrections=apply_corrections,
        ).run(text)
        return result.cleaned_text

    if shutil.which("ocr-cleanup"):
        cmd = ["ocr-cleanup"]
        if llm and llm != "none":
            cmd.extend(["--llm", llm])
        if model:
            cmd.extend(["--model", model])
        if apply_variants:
            cmd.append("--apply-variants")
        if not rejoin_linebreaks:
            cmd.append("--no-rejoin")
        if not apply_corrections:
            cmd.append("--no-corrections")
        proc = subprocess.run(
            cmd,
            input=text,
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout

    raise RuntimeError(
        "ocr-cleanup not available — pip install -e . "
        "(or clone ../ocr-cleanup for a local fork)."
    )
