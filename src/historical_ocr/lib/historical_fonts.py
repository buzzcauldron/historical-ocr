"""Historical typeface profiles for detecting strange OCR letterforms."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

# Long s, thorn, eth, ash, oe, eszett, yogh, rotunda r, etc.
_EARLY_PRINT_CHARS = frozenset("ſþÞðÐæÆœŒßẞꝛꝝꝑȝ")
_FRACTUR_CHARS = frozenset("äöüÄÖÜßẞſ")
_MODERN_NEWS_ALIEN = frozenset("ſþÞðÐꝛꝝꝑȝ")
_LATIN_EXTENDED_OK = frozenset("àáâãäåèéêëìíîïòóôõöùúûüýÿçñ")

_DIGIT_IN_WORD_RE = re.compile(r"[A-Za-z]\d|\d[A-Za-z]")
_OCR_GARBAGE_RE = re.compile(r"[|_`^~\\]{2,}")
_MIXED_SCRIPT_RE = re.compile(
    r"[\u0400-\u04FF\u0370-\u03FF\u0600-\u06FF]"
)  # Cyrillic, Greek, Arabic blocks


@dataclass(frozen=True)
class HistoricalFontProfile:
    key: str
    label: str
    # Letters valid in this typeface (historical forms included).
    expected_letters: frozenset[str]
    # Letters from another era/typeface — likely wrong OCR or engine bleed.
    alien_letters: frozenset[str]
    # Always suspicious in running text (engine junk, wrong material).
    junk_letters: frozenset[str] = frozenset("|_@`^~\\")
    min_conf_strange: float = 72.0


@dataclass(frozen=True)
class FontLetterFinding:
    anomalous: bool
    keep: bool
    reason: str
    chars: tuple[str, ...] = ()


_PROFILES: dict[str, HistoricalFontProfile] = {
    "modern_roman": HistoricalFontProfile(
        key="modern_roman",
        label="Twentieth-century roman",
        expected_letters=frozenset(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "".join(_LATIN_EXTENDED_OK)
        ),
        alien_letters=_MODERN_NEWS_ALIEN | _EARLY_PRINT_CHARS,
        min_conf_strange=70.0,
    ),
    "antiqua_roman": HistoricalFontProfile(
        key="antiqua_roman",
        label="Antiqua / enlightenment roman",
        expected_letters=frozenset(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "".join(_EARLY_PRINT_CHARS | _LATIN_EXTENDED_OK)
        ),
        alien_letters=frozenset("ꝛꝝꝑȝ"),  # rotunda forms rare in pure antiqua
        min_conf_strange=68.0,
    ),
    "blackletter": HistoricalFontProfile(
        key="blackletter",
        label="English blackletter",
        expected_letters=frozenset(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "".join(_EARLY_PRINT_CHARS | _LATIN_EXTENDED_OK)
        ),
        alien_letters=frozenset("äöüÄÖÜ"),  # German umlaut on English blackletter page
        min_conf_strange=65.0,
    ),
    "fraktur": HistoricalFontProfile(
        key="fraktur",
        label="German Fraktur",
        expected_letters=frozenset(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "".join(_EARLY_PRINT_CHARS | _FRACTUR_CHARS | _LATIN_EXTENDED_OK)
        ),
        alien_letters=frozenset("ꝛꝝ"),  # English rotunda on Fraktur page
        min_conf_strange=65.0,
    ),
    "secretary": HistoricalFontProfile(
        key="secretary",
        label="English secretary hand (print facsimile)",
        expected_letters=frozenset(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "".join(_EARLY_PRINT_CHARS | _LATIN_EXTENDED_OK)
        ),
        alien_letters=_FRACTUR_CHARS,
        min_conf_strange=65.0,
    ),
}


def list_font_profiles() -> list[str]:
    return sorted(_PROFILES)


@lru_cache(maxsize=32)
def resolve_font_profile(
    *,
    typeface: str = "",
    script: str = "",
    era: str = "",
    language: str = "",
) -> HistoricalFontProfile:
    """Pick the expected letter repertoire from print doc-type metadata."""
    tf = (typeface or "").strip().lower()
    sc = (script or "").strip().lower()
    er = (era or "").strip().lower()
    lang = (language or "").strip().lower()

    if sc in ("fraktur", "latf") or tf == "fraktur" or "fraktur" in er:
        return _PROFILES["fraktur"]
    if "secretary" in tf or "secretary" in er:
        return _PROFILES["secretary"]
    if tf == "blackletter" or "blackletter" in er:
        return _PROFILES["blackletter"]
    if er in ("twentieth_century", "contemporary") or "twentieth" in er or "1900" in er:
        return _PROFILES["modern_roman"]
    if er in ("contemporary_print", "modern_historical") or "2000" in er:
        return _PROFILES["modern_roman"]
    if lang.startswith("de") and er in ("early_modern", "nineteenth_century"):
        return _PROFILES["fraktur"]
    return _PROFILES["antiqua_roman"]


def _letter_chars(text: str) -> list[str]:
    return [ch for ch in text if ch.isalpha() or ch in _EARLY_PRINT_CHARS]


def analyze_token_for_font(
    text: str,
    profile: HistoricalFontProfile,
    *,
    conf: float,
) -> FontLetterFinding | None:
    """Return a finding when OCR letters look wrong for the document typeface."""
    token = text.strip()
    if not token or is_symbol_only_token(token):
        return None

    strange: list[str] = []
    reasons: list[str] = []

    for ch in _letter_chars(token):
        if ch in profile.junk_letters:
            strange.append(ch)
            reasons.append(f"junk:{ch}")
            continue
        if ch in profile.alien_letters:
            strange.append(ch)
            reasons.append(f"alien:{ch}:{profile.key}")
            continue
        if unicodedata.category(ch).startswith("L") and ch not in profile.expected_letters:
            if _MIXED_SCRIPT_RE.search(ch):
                strange.append(ch)
                reasons.append(f"script_bleed:{ch}")
            elif ord(ch) > 127 and ch not in _LATIN_EXTENDED_OK and ch not in _EARLY_PRINT_CHARS:
                strange.append(ch)
                reasons.append(f"unexpected_unicode:{ch}")

    if _DIGIT_IN_WORD_RE.search(token) and any(ch.isalpha() for ch in token):
        reasons.append("digit_in_word")
    if _OCR_GARBAGE_RE.search(token):
        reasons.append("ocr_garbage")

    if not strange and "digit_in_word" not in reasons and "ocr_garbage" not in reasons:
        return None

    keep = conf >= profile.min_conf_strange and not strange
    if strange and conf >= profile.min_conf_strange:
        keep = True  # flag for review but retain diplomatic text
    if strange and conf < profile.min_conf_strange - 10:
        keep = False

    reason = "strange_letter:" + ",".join(dict.fromkeys(reasons))
    return FontLetterFinding(
        anomalous=True,
        keep=keep,
        reason=reason,
        chars=tuple(dict.fromkeys(strange)),
    )


def is_symbol_only_token(token: str) -> bool:
    token = token.strip()
    if not token:
        return True
    return not any(ch.isalnum() or ch in _EARLY_PRINT_CHARS for ch in token)


def token_needs_font_review(
    text: str,
    profile: HistoricalFontProfile | None,
    *,
    conf: float,
) -> bool:
    if profile is None:
        return False
    finding = analyze_token_for_font(text, profile, conf=conf)
    return finding is not None and finding.anomalous


def line_has_strange_letters(
    text: str,
    profile: HistoricalFontProfile | None,
    *,
    conf: float,
) -> bool:
    if profile is None or not text.strip():
        return False
    for token in re.findall(r"\S+", text):
        if token_needs_font_review(token, profile, conf=conf):
            return True
    return False
