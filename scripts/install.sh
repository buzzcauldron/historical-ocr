#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="$(cd "$ROOT/.." && pwd)"
VENV="$ROOT/.venv"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip
pip install -e "$ROOT[all]"

# System Tesseract (print OCR engine)
if command -v tesseract >/dev/null 2>&1; then
  echo "→ tesseract: $(tesseract --version 2>&1 | head -1)"
else
  echo "→ installing tesseract…"
  if command -v brew >/dev/null 2>&1; then
    brew install tesseract tesseract-lang
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y \
      tesseract-ocr poppler-utils \
      tesseract-ocr-eng tesseract-ocr-lat tesseract-ocr-deu \
      tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa \
      tesseract-ocr-script-fraktur || true
  else
    echo "  warn: install tesseract manually (see README)"
  fi
fi

# Optional siblings (not required for core install)
if [[ -d "$PROJECTS/ocr-cleanup" ]]; then
  echo "→ editable: ocr-cleanup (Ted Underwood rules)"
  pip install -e "$PROJECTS/ocr-cleanup"
else
  echo "→ note: ../ocr-cleanup not found — print --clean will be skipped"
  echo "  Clone DataMunging fork or: git clone <ocr-cleanup-url> $PROJECTS/ocr-cleanup"
fi

if [[ -d "$PROJECTS/bib-ocr" ]]; then
  echo "→ editable: bib-ocr (PDF bibliography citation cascade)"
  pip install -e "$PROJECTS/bib-ocr"
else
  echo "→ note: ../bib-ocr not found — historical-ocr bib-ocr subcommand unavailable"
fi

[[ -f "$ROOT/.env" ]] || cp "$ROOT/.env.example" "$ROOT/.env"

echo ""
echo "Done. Activate: source $VENV/bin/activate"
historical-ocr --version
historical-ocr tools
