#!/usr/bin/env bash
# Login-node fetch for page-CNN data on Bridges2 (no GPU).
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${PAGE_CNN_DATA:-$ROOT/data/page_cnn}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

source "$VENV/bin/activate"
cd "$ROOT"

python scripts/fetch_page_cnn_data.py \
  --out "$DATA" \
  --all-hf \
  ${PAGE_CNN_LIMIT:+--limit "$PAGE_CNN_LIMIT"}

historical-ocr cnn sources
python scripts/fetch_page_cnn_data.py --list
