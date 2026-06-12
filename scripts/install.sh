#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="$(cd "$ROOT/.." && pwd)"
VENV="$ROOT/.venv"

# ── macOS: system Tk required by tkinterdnd2 (GUI drag-and-drop) ─────────────
# Homebrew Python does not bundle tkinter; install python-tk before creating the venv.
if [[ "$(uname)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "→ installing python-tk@${PY_VER} (required for GUI)…"
    brew install "python-tk@${PY_VER}" || brew install python-tk || true
  else
    echo "→ tkinter: OK"
  fi
fi

# ── Virtual environment + Python deps ────────────────────────────────────────
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip setuptools wheel
pip install -e "$ROOT"

# ── Playwright browsers (strigil / transcriber-shell) ────────────────────────
if python -c "import playwright" 2>/dev/null; then
  echo "→ playwright: installing chromium…"
  python -m playwright install chromium || echo "  warn: playwright install chromium failed"
fi

# ── System Tesseract + Poppler (print OCR engine) ────────────────────────────
if command -v tesseract >/dev/null 2>&1; then
  echo "→ tesseract: $(tesseract --version 2>&1 | head -1)"
else
  echo "→ installing tesseract…"
  if command -v brew >/dev/null 2>&1; then
    brew install tesseract tesseract-lang poppler
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y \
      tesseract-ocr poppler-utils \
      tesseract-ocr-eng tesseract-ocr-lat tesseract-ocr-deu \
      tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa \
      tesseract-ocr-script-fraktur || true
  else
    echo "  warn: install tesseract manually — brew install tesseract tesseract-lang poppler"
  fi
fi

# Verify poppler (pdf2image dependency)
if ! command -v pdftoppm >/dev/null 2>&1; then
  echo "  warn: poppler not found (needed for PDF → image); install: brew install poppler"
fi

# ── Optional editable siblings (override PyPI/git installs for local dev) ────
if [[ -d "$PROJECTS/ocr-cleanup" ]]; then
  echo "→ editable override: ocr-cleanup"
  pip install -e "$PROJECTS/ocr-cleanup"
fi

if [[ -d "$PROJECTS/manuscript-fingerprint" ]]; then
  echo "→ editable override: manuscript-fingerprint"
  pip install -e "$PROJECTS/manuscript-fingerprint"
elif [[ -d "$PROJECTS/typebox-fingerprinter" ]]; then
  echo "→ editable override: typebox-fingerprinter"
  pip install -e "$PROJECTS/typebox-fingerprinter"
fi

if [[ -d "$PROJECTS/bib-ocr" ]]; then
  echo "→ editable override: bib-ocr"
  pip install -e "$PROJECTS/bib-ocr"
fi

if [[ -d "$PROJECTS/transcription-shell" ]]; then
  echo "→ editable override: transcriber-shell"
  pip install -e "$PROJECTS/transcription-shell"
fi

if [[ -d "$PROJECTS/strigil" ]]; then
  echo "→ editable override: strigil"
  pip install -e "$PROJECTS/strigil"
fi

# ── .env ─────────────────────────────────────────────────────────────────────
[[ -f "$ROOT/.env" ]] || cp "$ROOT/.env.example" "$ROOT/.env"

echo ""
echo "Done. Activate: source $VENV/bin/activate"
echo "Add API keys to $ROOT/.env then run: historical-ocr-gui"
historical-ocr --version
historical-ocr tools
