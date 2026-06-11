"""Drop low-confidence symbol junk and strip column-rule artifacts from print OCR."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tesseract reports confidence on a 0–100 scale.
DEFAULT_MIN_CONFIDENCE = 60.0
DEFAULT_CHAR_BLACKLIST = "|_"
DEFAULT_STRIP_TRAILING = "|_:"
DEFAULT_ALWAYS_DROP = frozenset("|_")
DEFAULT_ORPHAN_LINE_CHARS = frozenset("1lI|_@.`:")


@dataclass(frozen=True)
class SymbolFilterOptions:
    enabled: bool = True
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    char_blacklist: str | None = DEFAULT_CHAR_BLACKLIST
    char_whitelist: str | None = None
    strip_trailing: str = DEFAULT_STRIP_TRAILING
    always_drop_chars: frozenset[str] = DEFAULT_ALWAYS_DROP
    glyph_filter: bool = True
    save_glyph_heatmap: bool = False
    drop_orphan_lines: bool = True
    orphan_line_chars: frozenset[str] = DEFAULT_ORPHAN_LINE_CHARS
    font_profile: object | None = None


def resolve_symbol_filter(settings, spec=None) -> SymbolFilterOptions:
    """Merge global settings with optional print doc-type overrides."""
    enabled = getattr(settings, "symbol_filter", True)
    min_conf = float(getattr(settings, "ocr_min_confidence", DEFAULT_MIN_CONFIDENCE))
    blacklist = getattr(settings, "tesseract_char_blacklist", None)
    whitelist = getattr(settings, "tesseract_char_whitelist", None)
    strip = str(getattr(settings, "symbol_strip_trailing", DEFAULT_STRIP_TRAILING))
    glyph_filter = bool(getattr(settings, "symbol_glyph_filter", True)) and enabled
    save_heatmap = (
        bool(getattr(settings, "symbol_glyph_heatmap", True))
        and glyph_filter
        and getattr(settings, "save_layout_artifacts", True)
        and not getattr(settings, "fast_mode", False)
    )

    font_profile = None
    if spec is not None:
        if getattr(spec, "tesseract_char_blacklist", None):
            blacklist = spec.tesseract_char_blacklist
        if getattr(spec, "tesseract_char_whitelist", None):
            whitelist = spec.tesseract_char_whitelist
        if glyph_filter:
            from historical_ocr.lib.historical_fonts import resolve_font_profile

            font_profile = resolve_font_profile(
                typeface=getattr(spec, "typeface", "") or "",
                script=getattr(spec, "script", "") or "",
                era=getattr(spec, "era", "") or "",
                language=getattr(spec, "language", "") or "",
            )

    always_drop = frozenset(blacklist) if blacklist else DEFAULT_ALWAYS_DROP

    orphan_chars = frozenset(
        getattr(settings, "symbol_orphan_line_chars", "") or DEFAULT_ORPHAN_LINE_CHARS,
    )

    return SymbolFilterOptions(
        enabled=enabled,
        min_confidence=min_conf,
        char_blacklist=blacklist,
        char_whitelist=whitelist,
        strip_trailing=strip,
        always_drop_chars=always_drop,
        glyph_filter=glyph_filter,
        save_glyph_heatmap=save_heatmap,
        drop_orphan_lines=bool(getattr(settings, "symbol_drop_orphan_lines", True)) and enabled,
        orphan_line_chars=orphan_chars,
        font_profile=font_profile,
    )


def is_symbol_only(token: str) -> bool:
    """True when the token has no letters or digits (punctuation / rules only)."""
    token = token.strip()
    if not token:
        return True
    return not any(ch.isalnum() for ch in token)


def should_drop_token(
    text: str,
    conf: float,
    opts: SymbolFilterOptions,
    *,
    glyph_decision=None,
) -> bool:
    if not opts.enabled:
        return False
    token = text.strip()
    if not token:
        return True

    if opts.glyph_filter and glyph_decision is not None:
        if glyph_decision.keep:
            return False
        return True

    if len(token) == 1 and token in opts.always_drop_chars:
        return True
    if is_symbol_only(token) and conf < opts.min_confidence:
        return True
    return False


def needs_glyph_review(text: str, conf: float, opts: SymbolFilterOptions) -> bool:
    """True when ink-shape analysis should override a naive drop/keep."""
    if not opts.enabled or not opts.glyph_filter:
        return False
    token = text.strip()
    if not token:
        return False
    if len(token) == 1 and token in opts.always_drop_chars:
        return True
    if is_symbol_only(token):
        return True
    if conf < opts.min_confidence:
        return True
    if opts.font_profile is not None:
        from historical_ocr.lib.historical_fonts import token_needs_font_review

        if token_needs_font_review(token, opts.font_profile, conf=conf):
            return True
    return False


def is_orphan_damage_line(line: str, opts: SymbolFilterOptions) -> bool:
    """True when a whole line is a single scan-damage mark (not real text)."""
    if not opts.drop_orphan_lines:
        return False
    token = line.strip()
    if not token:
        return True
    parts = token.split()
    if len(parts) != 1:
        return False
    ch = parts[0]
    if len(ch) == 1 and ch in opts.orphan_line_chars:
        return True
    if len(ch) == 1 and ch.isdigit():
        return True
    if len(ch) == 1 and ch in opts.always_drop_chars:
        return True
    return False


def sanitize_line(line: str, opts: SymbolFilterOptions) -> str:
    """Remove isolated rule junk and trailing column separators from one line."""
    if not opts.enabled:
        return line

    line = line.strip()
    if not line:
        return line

    parts: list[str] = []
    for part in line.split():
        if len(part) == 1 and part in opts.always_drop_chars:
            continue
        if is_symbol_only(part) and all(ch in opts.strip_trailing for ch in part):
            continue
        parts.append(part)

    line = " ".join(parts)
    if not line:
        return line

    trail = re.escape(opts.strip_trailing)
    line = re.sub(rf"[{trail}]+$", "", line)
    line = re.sub(r"([\w])[|_]+$", r"\1", line)
    return line.strip()


def sanitize_ocr_text(text: str, opts: SymbolFilterOptions) -> str:
    lines: list[str] = []
    for ln in text.splitlines():
        if is_orphan_damage_line(ln, opts):
            continue
        clean = sanitize_line(ln, opts)
        if clean:
            lines.append(clean)
    return "\n".join(lines).strip()
