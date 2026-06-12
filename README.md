# historical-ocr

Self-contained orchestrator for **computational-ready text** from historical sources.

**New here?** See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — plain-language setup, GUI walkthrough, and what `document.txt` / `document.xml` mean (no OCR jargon required).

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

### macOS (recommended: one-line installer)

```bash
bash scripts/install.sh
```

This handles everything: venv creation, all Python deps, system Tesseract + poppler via Homebrew, and the macOS-specific `python-tk` dependency required for the GUI. After it finishes:

```bash
source .venv/bin/activate
# Add API keys (Anthropic / Google) then launch the GUI:
historical-ocr-gui
```

**Prerequisites:** [Homebrew](https://brew.sh) must be installed. The script will prompt for your password if it needs to install system packages.

### macOS (manual)

```bash
# 1. System packages (Homebrew)
brew install tesseract tesseract-lang poppler

# tkinter is not bundled with Homebrew Python — install the matching version:
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
brew install "python-tk@${PY_VER}"

# 2. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium

# 3. API keys
cp .env.example .env   # edit to add ANTHROPIC_API_KEY / GOOGLE_API_KEY
```

### Debian / Ubuntu

```bash
sudo apt install tesseract-ocr poppler-utils \
  tesseract-ocr-eng tesseract-ocr-lat tesseract-ocr-deu \
  tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa \
  tesseract-ocr-script-fraktur \
  python3-tk

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium
cp .env.example .env
```

### Verify

```bash
historical-ocr --version
historical-ocr tools          # confirm tesseract, poppler, playwright on PATH
historical-ocr tesseract -v   # show Tesseract version + installed language packs
```

### API keys (optional — needed for LLM cleanup tiers)

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...   # medium/high tier: Haiku 4.5 / Sonnet 4.6
GOOGLE_API_KEY=AIza...         # high tier: Gemini 2.5 Pro
```

Without keys the pipeline runs free-tier (Tesseract + Underwood rules only).

### Companion tools (optional)

`transcriber-shell`, `strigil`, and `playwright` are included in `pip install -e .`. For local development overrides or Kraken HTR extras:

```bash
pip install -e ../transcription-shell[kraken,gemini,pdf]
pip install -e ../strigil
```

## Outputs

```
jobs/<job_id>/
  manifest.json          # full job state
  pages/                 # normalized page images
  artifacts/<page_id>/   # per-page OCR intermediates
    ocr.txt              # raw Tesseract output
    clean.txt            # Underwood-normalized text
    layout_ocr.txt       # layout-aware OCR (when columns/sections detected)
  export/
    {source_stem}.txt              # merged clean reading text (all pages)
    {source_stem}.xml              # merged TEI P5 (+ facsimile when layout exists)
    {source_stem}.delivery.json    # provenance + normalization policy
    {source_stem}.checksums.sha256
    _internal/           # per-page debug artifacts
      txt/ xml/ tei/ corpus.jsonl
```

## Desktop GUI

```bash
historical-ocr-gui       # or: historical-ocr gui
```

Drag-and-drop files or folders, paste a URL, choose a quality tier, and click Run. The log panel shows every pipeline step in real time. Outputs land under `jobs/<job_id>/export/`.

Quality tiers:
- **Free** — Tesseract + Underwood rules, no API key needed
- **Medium** — adds Haiku 4.5 spot-LLM repair for damaged lines
- **High** — full Sonnet 4.6 / Gemini 2.5 Pro cleanup pass

## Usage

```bash
# Print: auto-routed diachronic OCR (1500–present) + Underwood clean
historical-ocr run demo -i book_1850.pdf --mode print --publication-year 1850

# Print OCR only, skip normalization
historical-ocr run eebo-demo -i book.pdf --mode print --no-clean

# Fetch from URL (IIIF / direct image / PDF)
historical-ocr run hathitrust-vol --url "https://…" --mode print

# Manuscript: needs transcriber-shell + prompt YAML
historical-ocr run walters-w25 \
  -i page.jpg \
  --mode manuscript \
  --prompt ../transcription-shell/scripts/latin_ms/prompt_charter.yaml

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
historical-ocr bib-ocr paper.pdf   # bibliography citation cascade
historical-ocr ecosystem   # catalog of related tools
historical-ocr print-types # era/doc-type profiles

# Page CNN for --mode auto (print vs manuscript routing)
historical-ocr cnn sources
historical-ocr cnn fetch --source ocr-quality --source ocr-pdf-degraded
historical-ocr cnn train --out models/page_cnn.pt
# HISTORICAL_OCR_PAGE_CNN_MODEL=models/page_cnn.pt historical-ocr run job -i book.pdf --mode auto
# See docs/PAGE_CNN_TRAINING.md

bash scripts/test_versions.sh   # smoke test: assert export/txt + export/xml
pytest
```

## License

MIT — [LICENSE](LICENSE). Vendored snippets retain attribution in [docs/VENDOR.md](docs/VENDOR.md).
