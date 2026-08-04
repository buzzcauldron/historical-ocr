# historical-ocr

Self-contained Python package for **computational-ready text** from historical sources — print OCR (Tesseract + diachronic profiles), optional LLM cleanup, TEI export, and a desktop GUI.

**New here?** See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — plain-language setup, GUI walkthrough, and what `document.txt` / `document.xml` mean.

| | |
|--|--|
| **Version** | 0.2.0 |
| **Requires** | Python ≥ 3.11 |
| **Commands** | `historical-ocr`, `historical-ocr-gui` |
| **License** | MIT |

## Package extras

| Extra | What you get |
|-------|----------------|
| *(default)* | Print OCR pipeline, GUI, Playwright fetch, LLM client libs |
| `[ecosystem]` | Sibling tools: `ocr-cleanup`, `bib-ocr`, `strigil` (via GitHub) |
| `[ml]` | Torch, TrOCR, page-CNN training, YOLO figure tools |
| `[full]` | `[ecosystem]` + `[ml]` |
| `[dev]` | pytest + `[full]` |

System tools **Tesseract** and **poppler** are not pip packages; install them with Homebrew/apt (or `scripts/install.sh`).

## What lives here vs elsewhere

| Capability | In this package | External tool (optional) |
|------------|-----------------|---------------------------|
| URL / IIIF fetch | `lib/fetch.py` | — |
| PDF → page images | `lib/pdf_pages.py` | poppler (`pdftoppm`) |
| Print OCR | `backends/tesseract.py`, `lib/print_ocr.py` | `tesseract` |
| Print doc-type profiles | `document_types/print/*.yaml` (shipped in the wheel) | — |
| Protocol → text / TEI | `lib/protocol_text.py`, `lib/tei_minimal.py` | — |
| Manuscript transcription | `backends/transcriber_shell.py` | [transcription-shell](https://github.com/buzzcauldron/transcription-shell) |
| Type-case fingerprint | `backends/fingerprint.py` | [manuscript-fingerprint](https://github.com/buzzcauldron/manuscript-fingerprint) |
| Print OCR normalization | `backends/ocr_cleanup.py` | [ocr-cleanup](https://github.com/buzzcauldron/ocr-cleanup) (`pip install '.[ecosystem]'`) |

See [docs/VENDOR.md](docs/VENDOR.md) and [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Install

### One-line (clone + venv + system deps)

```bash
git clone https://github.com/buzzcauldron/historical-ocr.git
cd historical-ocr
bash scripts/install.sh
source .venv/bin/activate
historical-ocr --version    # → historical-ocr 0.2.0
```

### Editable (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e ".[ecosystem]"   # core + sibling GitHub packages
python -m playwright install chromium
cp .env.example .env            # optional API keys
```

### From GitHub (no local checkout)

```bash
pip install "git+https://github.com/buzzcauldron/historical-ocr.git"
# optional:
# pip install "historical-ocr[ecosystem] @ git+https://github.com/buzzcauldron/historical-ocr.git"
# pip install "historical-ocr[ml] @ git+https://github.com/buzzcauldron/historical-ocr.git"
```

After a normal wheel/git install you can run `historical-ocr` from any directory. Set `HISTORICAL_OCR_ROOT` or `HISTORICAL_OCR_JOBS_DIR` if jobs / `.env` should live outside the current working directory.

### Build a wheel locally

```bash
pip install build
python -m build --wheel
# installs: pip install dist/historical_ocr-*.whl
```

### System packages (print OCR)

| Platform | Packages |
|----------|----------|
| **macOS** | `brew install tesseract tesseract-lang poppler` and matching `python-tk@…` for the GUI |
| **Debian / Ubuntu** | `sudo apt install tesseract-ocr poppler-utils python3-tk` (+ packs e.g. `tesseract-ocr-ell` / `tesseract-ocr-grc` for Greek) |

### Verify

```bash
historical-ocr --version
historical-ocr tools          # tesseract, poppler, playwright on PATH
historical-ocr tesseract -v   # version + language packs
historical-ocr print-types    # built-in era/doc-type profiles
```

### API keys (optional — LLM tiers)

Edit `.env` (from `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...   # medium/high: Haiku / Sonnet
GOOGLE_API_KEY=AIza...         # high: Gemini
```

Without keys the free tier runs Tesseract (+ Underwood rules when `ocr-cleanup` is installed).

### Companion tools (optional local overrides)

```bash
pip install -e .[ecosystem]
# or editable siblings next to this repo:
pip install -e ../ocr-cleanup ../bib-ocr ../strigil
pip install -e ../transcription-shell[kraken,gemini,pdf]   # manuscript HTR
```

## Desktop GUI

```bash
historical-ocr-gui       # or: historical-ocr gui
```

Drag-and-drop files or folders, paste a URL, choose a quality tier, and click Run. Outputs land under `jobs/<job_id>/export/`.

| Tier | Behavior |
|------|----------|
| **Free** | Tesseract + Underwood rules |
| **Medium** | + Haiku spot-LLM repair |
| **High** | + Sonnet / Gemini full cleanup |

## Usage

```bash
# Print: diachronic OCR (doc type / year) + clean
historical-ocr run demo -i book_1850.pdf --mode print --publication-year 1850

# Skip normalization
historical-ocr run eebo-demo -i book.pdf --mode print --no-clean

# Fetch URL (IIIF / image / PDF)
historical-ocr run hathitrust-vol --url "https://…" --mode print

# Manuscript (needs transcription-shell + prompt YAML)
historical-ocr run walters-w25 \
  -i page.jpg \
  --mode manuscript \
  --prompt ../transcription-shell/scripts/latin_ms/prompt_charter.yaml

historical-ocr status <job_id>
historical-ocr export <job_id>
```

## Outputs

```
jobs/<job_id>/
  manifest.json
  pages/
  artifacts/<page_id>/
    ocr.txt
    clean.txt
    layout_ocr.txt
  export/
    {source_stem}.txt
    {source_stem}.xml
    {source_stem}.delivery.json
    {source_stem}.checksums.sha256
    _internal/           # per-page txt/xml/tei + corpus.jsonl
```

## CLI reference

```
historical-ocr run <job_id> [--url URL] [-i FILE ...]
                 [--mode auto|manuscript|print] [--prompt YAML] [--fingerprint]
historical-ocr acquire <job_id> [--url URL] [-i FILE ...]
historical-ocr export <job_id>
historical-ocr status <job_id>
historical-ocr tools
historical-ocr tesseract
historical-ocr bib-ocr paper.pdf
historical-ocr ecosystem
historical-ocr print-types

# Page CNN for --mode auto (print vs manuscript)
historical-ocr cnn sources
historical-ocr cnn fetch --source ocr-quality --source ocr-pdf-degraded
historical-ocr cnn train --out models/page_cnn.pt
# HISTORICAL_OCR_PAGE_CNN_MODEL=models/page_cnn.pt historical-ocr run job -i book.pdf --mode auto
# See docs/PAGE_CNN_TRAINING.md

bash scripts/test_versions.sh
pytest
```

## License

MIT — [LICENSE](LICENSE). Vendored snippets retain attribution in [docs/VENDOR.md](docs/VENDOR.md).
