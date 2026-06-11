# Diachronic print OCR (1500–present)

historical-ocr routes **print** pages through YAML **document types** and an **OCR combination** planner — the same layering as transcription-shell's `doc_type` + `htr_combination`.

## Orthogonal selectors

Two independent axes combine when `--print-doc-type auto` (default):

| Axis | Flag / env | Example |
|------|------------|---------|
| **Language** | `--print-language` / `HISTORICAL_OCR_PRINT_LANGUAGE` | `de`, `la`, `fr`, `en`, `auto` |
| **Year** | `--publication-year` / filename / `HISTORICAL_OCR_PUBLICATION_YEAR` | `1688`, `1850` |

```bash
historical-ocr run job -i book.pdf --print-language de --publication-year 1720
# → german_fraktur + deu_latf Tesseract stack
```

Languages: `auto`, `en`, `la`, `de`, `fr`, `it`, `es`. Each has its own era→profile matrix.

Explicit `--print-doc-type` still accepts a language overlay on the Tesseract stack.

## Chronology (English default)

When language is `en` or `auto`, publication year selects:

| Years | Document type | Tesseract stack |
|-------|---------------|-----------------|
| 1475–1499 | `eebo_blackletter` | `lat+frk+eng` |
| 1500–1700 | `early_modern_english` | `eng+lat+frk` |
| 1701–1800 | `enlightenment_antiqua` | `eng+lat` |
| 1801–1900 | `nineteenth_century` | `eng` |
| 1901–2000 | `twentieth_century` | `eng` (+ PDF text first) |
| 2001+ | `contemporary_print` | `eng` (+ PDF text first) |

Language overrides: German → `german_fraktur` (1600–1910); Latin → `humanist_roman` (1500–1700).

Provide a year via:

```bash
historical-ocr run job -i book_1850.pdf --publication-year 1850
# or embed a year in the filename: sermon_1688.pdf
```

## All document types

| Name | Era | Normalization |
|------|-----|---------------|
| `eebo_blackletter` | 1475–1640 | normalized |
| `humanist_roman` | 1500–1650 | diplomatic |
| `early_modern_english` | 1500–1700 | normalized |
| `german_fraktur` | 1600–1800 | normalized |
| `enlightenment_antiqua` | 1700–1800 | normalized |
| `nineteenth_century` | 1800–1900 | modern |
| `twentieth_century` | 1900–2000 | modern |
| `contemporary_print` | 2000+ | modern |
| `modern_historical` | 1900+ | alias / legacy |

```bash
historical-ocr print-types
```

## Symbol filter (column rules, junk marks)

Print OCR **drops non-letter junk by default** so Tesseract does not keep column rules as fake letters:

1. **Tesseract blacklist** — `tessedit_char_blacklist=|_` (modern newspaper profiles include this in YAML)
2. **Glyph / letterform gate** — for suspect tokens, crops each word box and classifies ink as **letterform**, **symbol**, **rule**, or **damage** (metrics adapted from manuscript-fingerprint). Rules and damage are never emitted; letterforms are kept even when OCR confidence is low.
3. **Line heatmap band** — per-line median letter height sets the expected type body band before classifying marks.
4. **Confidence gate** — fallback for tokens without glyph review
5. **Line sanitizer** — trailing `|_:` and isolated rule tokens stripped after OCR

```bash
historical-ocr run job -i scan.tif --mode print              # filter on (default)
historical-ocr run job -i scan.tif --mode print --no-symbol-filter
# TXT review companions (only when glyph filtering dropped marks):
#   export/{basename}.review.json   — what was removed from the TXT
#   export/{basename}.review.png    — heatmap of dropped boxes only
historical-ocr run job -i scan.tif --mode print --no-glyph-heatmap   # JSON only
```

Env: `HISTORICAL_OCR_SYMBOL_FILTER=0`, `HISTORICAL_OCR_SYMBOL_GLYPH_HEATMAP=0`, `HISTORICAL_OCR_TESSERACT_CHAR_BLACKLIST=|_`. Glyph decisions run during OCR (internal); review PNG/JSON are written at **export** beside the production `.txt`. `--fast` skips glyph review and review artifacts.

Per doc-type override in YAML: `ocr.char_blacklist: "|_"` (see `twentieth_century.yaml`).

## LLM-independent path (default for print)

Print OCR **does not require any LLM or API key**. The production path is:

1. **Tesseract** layout OCR (era-aware doc type from `--publication-year`)
2. **Symbol / glyph filter** — drop column rules, damage marks, orphan lines (`1`, `l`, `@`, …)
3. **Underwood rules** (`ocr-cleanup`) — hyphen rejoin, long-s, spelling corrections
4. **Post-clean sanitize** — second orphan-line pass after rules

```bash
# Low latency (recommended for batches): rules + clean, no glyph crops / review PNG
historical-ocr run job -i scan.tif --mode print --publication-year 1970 --low-latency

# Full rules-only with glyph review companions (~1s slower per page)
historical-ocr run job -i scan.tif --mode print --rules-only

# Fastest (~4–5s/page): raw Tesseract only, no clean
historical-ocr run job -i scan.tif --mode print --fast --no-clean
```

| Flag | ~BlackNews/page | Keeps |
|------|-----------------|-------|
| `--low-latency` | **~5 s** | Underwood clean, blacklist, orphan-line drop |
| `--rules-only` | **~6 s** | + glyph classify + `.review.png` |
| `--fast --no-clean` | **~4.5 s** | Raw OCR only |
| LLM clean | **~60 s** | Not recommended for batches |

Benchmark against scraped newspaper GT (Chronicling America, no LLM):

```bash
historical-ocr gt fetch --limit 200 --val-ratio 0.1
historical-ocr gt eval --gt-dir data/newspaper_gt --split val --limit 20
```

## Human corrections → tune rules

Submit edited text to learn replacements (no LLM):

```bash
# 1. Run OCR
historical-ocr run myjob -i scan.tif --mode print --low-latency

# 2. Copy export for editing
historical-ocr gt template myjob
# edit jobs/myjob/export/scan.corrected.txt

# 3. Import + mine rules
historical-ocr gt submit --job myjob
historical-ocr gt tune

# 4. Next runs apply data/user_gt/tuned_rules.json automatically
#    (or HISTORICAL_OCR_TUNE_RULES=/path/to/tuned_rules.json)
```

Evaluate tuned OCR against your corrections: `historical-ocr gt eval --gt-dir data/user_gt --split val`.

## OCR combinations

| Mode | Behavior |
|------|----------|
| `tesseract_then_clean` | Layout OCR + Underwood rules (default) |
| `tesseract_only` | Raw OCR |
| `pdf_text_first` | Embedded PDF text when sufficient (1900+ profiles) |
| `shell_print` | Fork to **transcriber-shell** |

## Usage

```bash
# Auto year routing (default)
historical-ocr run job -i walters_1920.pdf --mode print

# Explicit era
historical-ocr run job -i eebo_vol.pdf --print-doc-type early_modern_english

# German Fraktur
historical-ocr run job -i scan.pdf --print-doc-type german_fraktur --publication-year 1720
```

Env:

```
HISTORICAL_OCR_PRINT_DOC_TYPE=auto
HISTORICAL_OCR_PUBLICATION_YEAR=
TESSERACT_CMD=/opt/homebrew/bin/tesseract
TESSDATA_PREFIX=/opt/homebrew/share/tessdata
```

## Tesseract setup

Print OCR uses the system **Tesseract** binary via `backends/tesseract.py` (not vendored). Install language packs for historical scripts (`lat`, `frk`, `deu_latf`, etc.):

```bash
brew install tesseract tesseract-lang   # macOS
historical-ocr tesseract -v
historical-ocr tesseract --lang lat+frk+eng
historical-ocr tools                    # quick availability check
```

## Adding a new era

1. `document_types/print/my_era.yaml`
2. Optional `document_types/print/models/my_stack.yaml`
3. Add an `EraBand` in `src/historical_ocr/document_types/era_chronology.py` if it belongs on the auto timeline
