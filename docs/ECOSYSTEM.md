# Historical OCR ecosystem (GitHub crawl)

Curated tools that complement **historical-ocr**. Grouped by pipeline stage.

## Integrated in this repo

| Tool | GitHub | Role in historical-ocr |
|------|--------|------------------------|
| **ocr-cleanup** (Underwood rules) | Local fork of [tedunderwood/DataMunging](https://github.com/tedunderwood/DataMunging) | Print-route **clean** pass: `CorrectionRules`, linebreak rejoin, optional LLM stage |
| **transcription-shell** | [buzzcauldron/transcription-shell](https://github.com/buzzcauldron/transcription-shell) | Manuscript: lineation + protocol YAML (subprocess) |
| **manuscript-fingerprint** | [buzzcauldron/manuscript-fingerprint](https://github.com/buzzcauldron/manuscript-fingerprint) | Early modern print type-case ID (subprocess) |
| **strigil** | [sethstrickland/strigil](https://github.com/sethstrickland/strigil) | Full archival fetch (use directly for EEBO/HathiTrust crawl; we vendor minimal IIIF fetch) |

### Ted Underwood cleaner (detail)

Upstream: **[tedunderwood/DataMunging](https://github.com/tedunderwood/DataMunging)** — `OCRnormalizer/` + `/rulesets/` (CC-BY 3.0, English books after ~1700).

- Fixes long-s / f confusion, linebreak hyphenation, variant spellings, syncope (`remember'd` → `remembered`).
- Normalizes toward **modern British** spelling for **diachronic comparison** — not diplomatic reproduction.
- Newer local-only `pagefeatures/` branch preserves punctuation better; not merged upstream.

**Our path:** sibling **[ocr-cleanup](../ocr-cleanup)** wraps the rulesets in `ocr_cleanup.rules.apply_rules` and optional LLM passes. historical-ocr calls it after Tesseract print OCR (`jobs/<id>/clean/`).

```bash
pip install -e ../ocr-cleanup          # rules only
pip install -e '../ocr-cleanup[anthropic]'  # + LLM cleanup
historical-ocr run job -i book.pdf --mode print   # --clean on by default
historical-ocr run job -i book.pdf --mode print --no-clean
```

Env: `HISTORICAL_OCR_CLEAN_PRINT=0`, `HISTORICAL_OCR_CLEAN_VARIANTS=1`, `HISTORICAL_OCR_CLEAN_LLM=anthropic`.

---

## Acquire / digitization

| Tool | GitHub | Notes |
|------|--------|-------|
| **strigil** | [sethstrickland/strigil](https://github.com/sethstrickland/strigil) | IIIF, EEBO, HathiTrust, Internet Archive, CONTENTdm |
| **magic-elise-tool** | buzzcauldron (private) | Diplomatic abbreviation expander (sibling) |

---

## Segmentation & HTR / OCR engines

| Tool | GitHub | Notes |
|------|--------|-------|
| **kraken** | [mittagessen/kraken](https://github.com/mittagessen/kraken) | Layout + HTR; PageXML/ALTO; backbone for eScriptorium |
| **eScriptorium** | [escripta/escriptorium](https://github.com/escripta/escriptorium) | Web UI for Kraken training/inference |
| **Transkribus** | [Transkribus](https://transkribus.org/) (platform) | HTR models, API — no full OSS core |
| **OCR4all** | [OCR4all/OCR4all](https://github.com/OCR4all/OCR4all) | Historical print workflow GUI |
| **OCR-D** | [OCR-D](https://github.com/OCR-D) | German early-print modular pipeline |
| **Churro** | [stanford-oval/Churro](https://github.com/stanford-oval/Churro) | VLM toolkit + CHURRO-3B model |
| **co-ocr-htr** | [DigitalHumanitiesCraft/co-ocr-htr](https://github.com/DigitalHumanitiesCraft/co-ocr-htr) | Browser expert-in-the-loop PAGE-XML correction |
| **medieval-ocr-pipeline** | [yahyamomtaz/medieval-ocr-pipeline](https://github.com/yahyamomtaz/medieval-ocr-pipeline) | Kraken + TrOCR + ByT5 correction |
| **glyph_machina_public** | [ideasrule/glyph_machina_public](https://github.com/ideasrule/glyph_machina_public) | HTR training stack (used by transcription-shell) |

---

## Protocol, export, computational text

| Tool | GitHub | Notes |
|------|--------|-------|
| **transcription-protocol** | [buzzcauldron/transcription-protocol](https://github.com/buzzcauldron/transcription-protocol) | Evidence-grade YAML schema + TEI export |
| **transcription-shell** | [buzzcauldron/transcription-shell](https://github.com/buzzcauldron/transcription-shell) | Lineation → LLM → validated YAML |
| **expand-diplomatic** | buzzcauldron (sibling) | Abbreviation expansion for evaluation |
| **bib-ocr** | [buzzcauldron/bib-ocr](https://github.com/buzzcauldron/bib-ocr) | PDF bibliography OCR (research-party) |
| **research-party** | buzzcauldron (private) | Pack compiler, citation OCR ingest |

---

## Post-OCR correction & normalization

| Tool | GitHub | Notes |
|------|--------|-------|
| **DataMunging / OCRnormalizer** | [tedunderwood/DataMunging](https://github.com/tedunderwood/DataMunging) | Original Underwood cleaner + rulesets |
| **ocr-cleanup** | Local `../ocr-cleanup` | Packaged fork + optional LLM stages |
| **HIPE-OCRepair-scorer** | [hipe-eval/HIPE-OCRepair-scorer](https://github.com/hipe-eval/HIPE-OCRepair-scorer) | ICDAR 2026 post-correction metrics |
| **OCR-Text-Cleaning** | [FilippoCrc/OCR-Text-Cleaning](https://github.com/FilippoCrc/OCR-Text-Cleaning) | LLM char + paragraph cleaning (inspired ocr-cleanup) |

---

## Evaluation & attribution

| Tool | GitHub | Notes |
|------|--------|-------|
| **cthulhu-eval** | [cthulhu-eval](https://pypi.org/project/cthulhu-eval/) | WER/CER on PAGE-XML, ALTO, plain text |
| **manuscript-fingerprint** | [buzzcauldron/manuscript-fingerprint](https://github.com/buzzcauldron/manuscript-fingerprint) | Physical type-case fingerprint (EEBO era) |
| **medieval-stylometry** | buzzcauldron (sibling) | Stylometric analysis downstream |

---

## Suggested stacks

**Early modern English print (EEBO/Hathi):**
`strigil acquire` → `historical-ocr run --mode print` → Underwood clean → `corpus.jsonl`

**Manuscript / charter:**
`strigil` or local TIFF → `historical-ocr run --mode manuscript --prompt …` → protocol YAML + TEI

**Type-case attribution:**
`manuscript-fingerprint scan` on PDF → optional routing hint for `--mode auto`

---

*Last crawled: 2026-06-10. Run `historical-ocr ecosystem` to print this file.*
