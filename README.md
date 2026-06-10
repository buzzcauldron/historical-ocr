# historical-ocr

Self-contained orchestrator for **computational-ready text** from historical sources.

This repo vendors only the small, reusable pieces from sibling projects. Heavy tools run as **optional external CLIs** when installed on `PATH`.

## What lives here vs elsewhere

| Capability | In this repo | External tool (optional) |
|------------|--------------|---------------------------|
| URL / IIIF fetch | `lib/fetch.py` | — |
| PDF → page images | `lib/pdf_pages.py` | — |
| Print OCR | `lib/print_ocr.py` | `tesseract`, `poppler` |
| Protocol YAML → text / TEI | `lib/protocol_text.py`, `lib/tei_minimal.py` | — |
| Manuscript transcription | `backends/transcriber_shell.py` | [**transcription-shell**](https://github.com/buzzcauldron/transcription-shell) |
| Type-case fingerprint | `backends/fingerprint.py` | [**manuscript-fingerprint**](https://github.com/buzzcauldron/manuscript-fingerprint) |
| Print OCR normalization | `backends/ocr_cleanup.py` | Sibling [**ocr-cleanup**](../ocr-cleanup) ([Underwood DataMunging](https://github.com/tedunderwood/DataMunging)) |

See [docs/VENDOR.md](docs/VENDOR.md) and [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
cp .env.example .env   # add API keys for manuscript runs
```

System packages for print OCR:

```bash
# macOS
brew install tesseract poppler

# Debian/Ubuntu
sudo apt install tesseract-ocr poppler-utils
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
  manifest.json
  ocr/*.txt              # raw print OCR
  clean/*.txt            # Underwood-normalized (when ocr-cleanup installed)
  export/txt/<page>.txt  # per-page computational text (all routes)
  export/xml/<page>.xml  # per-page TEI P5 (all routes)
  export/corpus.jsonl    # one JSON object per page — NLP/ML ready
  export/corpus.txt
  export/tei/*.xml         # manuscript protocol TEI (when transcribed)
```

## Usage

```bash
# Print: OCR + Underwood clean (default)
historical-ocr run eebo-demo -i book.pdf --mode print

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
historical-ocr ecosystem   # catalog of related GitHub tools
bash scripts/test_versions.sh   # smoke: assert export/txt + export/xml
pytest tests/test_output_files.py
```

## License

MIT — [LICENSE](LICENSE). Vendored snippets retain attribution in [docs/VENDOR.md](docs/VENDOR.md).
