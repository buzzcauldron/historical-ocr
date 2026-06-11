# historical-ocr

Self-contained orchestrator for **computational-ready text** from historical sources.

**New here?** See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — plain-language setup, GUI walkthrough, and what `document.txt` / `document.xml` mean (no OCR jargon required).

This repo vendors only the small, reusable pieces from sibling projects. Heavy tools run as **optional external CLIs** when installed on `PATH`.

## What lives here vs elsewhere

| Capability | In this repo | External tool (optional) |
|------------|--------------|---------------------------|
| URL / IIIF fetch | `lib/fetch.py` | — |
| PDF → page images | `lib/pdf_pages.py` | — |
| Print OCR | `backends/tesseract.py`, `lib/print_ocr.py` | `tesseract`, `poppler` |
| Protocol YAML → text / TEI | `lib/protocol_text.py`, `lib/tei_minimal.py` | — |
| Manuscript transcription | `backends/transcriber_shell.py` | [**transcription-shell**](https://github.com/buzzcauldron/transcription-shell) |
| Type-case fingerprint | `backends/fingerprint.py` | [**manuscript-fingerprint**](https://github.com/buzzcauldron/manuscript-fingerprint) |
| Print OCR normalization | `backends/ocr_cleanup.py` | Sibling [**ocr-cleanup**](../ocr-cleanup) ([Underwood DataMunging](https://github.com/tedunderwood/DataMunging)) |

See [docs/VENDOR.md](docs/VENDOR.md) and [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add API keys for manuscript runs
```

System packages for print OCR (Tesseract + language packs):

```bash
# macOS
brew install tesseract tesseract-lang poppler

# Debian/Ubuntu
sudo apt install tesseract-ocr poppler-utils \
  tesseract-ocr-eng tesseract-ocr-lat tesseract-ocr-deu \
  tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa \
  tesseract-ocr-script-fraktur

historical-ocr tesseract -v          # verify binary + installed langs
historical-ocr tesseract --lang lat+frk+eng
```

Optional manuscript stack (install separately):

```bash
# From sibling checkouts or pip when available
pip install -e ../transcription-shell[pdf,gemini,kraken]
playwright install chromium
```

## Outputs

```
jobs/<job_id>/
  manifest.json          # full job state (internal)
  export/
    {source_stem}.txt              # production: one clean reading text (all pages)
    {source_stem}.xml              # production: one merged TEI P5 (+ facsimile when layout exists)
    {source_stem}.delivery.json    # provenance + normalization policy
    {source_stem}.checksums.sha256   # SHA-256 for the production txt + xml
    _internal/           # per-page debug / ML (not shipped by default)
      txt/ xml/ tei/ corpus.jsonl
  ocr/*.txt              # raw print OCR (internal)
  clean/*.txt            # Underwood-normalized (internal)
  *.review.png           # optional glyph-machina heatmap for problem pages
  *.review.json          # glyph-machina metadata for dropped/low-confidence glyphs
```

## Desktop GUI

```bash
pip install -e .    # includes tkinterdnd2 for drag-and-drop
historical-ocr gui
# or: historical-ocr-gui
```

The GUI mirrors **transcriber-shell**: file list, job options, normalization settings (max width / JPEG quality), background worker thread, and log panel. Outputs land under `jobs/<job_id>/export/`.

## Usage

```bash
# Print: auto-routed diachronic OCR (1500–present) + Underwood clean
historical-ocr run demo -i book_1850.pdf --mode print --publication-year 1850

# List era profiles and chronology
historical-ocr print-types

# Print OCR only, skip normalization
historical-ocr run eebo-demo -i book.pdf --mode print --no-clean

# Manuscript: needs transcriber-shell on PATH + prompt YAML
historical-ocr run walters-w25 \
  -i page.jpg \
  --mode manuscript \
  --prompt ../transcription-shell/scripts/latin_ms/prompt_charter.yaml

# Fetch from URL (IIIF / direct image / PDF)
historical-ocr run hathitrust-vol --url "https://…" --mode auto --fingerprint

historical-ocr status <job_id>
historical-ocr export <job_id>
```

## CLI

```
historical-ocr run <job_id> [--url URL] [-i FILE ...]
                 [--mode auto|manuscript|print] [--prompt YAML] [--fingerprint]
historical-ocr acquire <job_id> [--url URL] [-i FILE ...]
historical-ocr export <job_id>
historical-ocr status <job_id>
historical-ocr tools       # which external CLIs are on PATH
historical-ocr tesseract   # Tesseract version + language packs
historical-ocr bib-ocr paper.pdf   # optional: full citation cascade (pip install -e ../bib-ocr)
historical-ocr ecosystem   # catalog of related GitHub tools

# Page CNN for --mode auto (print vs manuscript routing)
pip install -e ".[ml]"
historical-ocr cnn sources
historical-ocr cnn fetch --source ocr-quality --source ocr-pdf-degraded
historical-ocr cnn train --out models/page_cnn.pt
# HISTORICAL_OCR_PAGE_CNN_MODEL=models/page_cnn.pt
historical-ocr run job -i book.pdf --mode auto
# See docs/PAGE_CNN_TRAINING.md (OCR-Quality, pixparse, OCRDatasets, Bridges/Akdeniz)
bash scripts/test_versions.sh   # smoke: assert export/txt + export/xml
pytest tests/test_output_files.py
```

## License

MIT — [LICENSE](LICENSE). Vendored snippets retain attribution in [docs/VENDOR.md](docs/VENDOR.md).
