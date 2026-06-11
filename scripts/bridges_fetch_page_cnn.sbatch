#!/bin/bash
#SBATCH -J page-cnn-fetch
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 06:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
# Download page-CNN training images on Bridges (CPU; no GPU needed).
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${PAGE_CNN_DATA:-$ROOT/data/page_cnn}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"
mkdir -p "$DATA/print" "$DATA/manuscript"

LIMIT_ARGS=()
if [[ -n "${PAGE_CNN_LIMIT:-}" ]]; then
  LIMIT_ARGS=(--limit "$PAGE_CNN_LIMIT")
fi

python scripts/fetch_page_cnn_data.py \
  --out "$DATA" \
  --source ocr-quality \
  --source ocr-pdf-degraded \
  "${LIMIT_ARGS[@]}"

# Optional pixparse sample (set PAGE_CNN_PIXPARSE_LIMIT=500 to enable in submit script).
if [[ -n "${PAGE_CNN_PIXPARSE_LIMIT:-}" ]]; then
  python scripts/fetch_page_cnn_data.py \
    --out "$DATA" \
    --source pixparse-pdfa \
    --source pixparse-idl \
    --limit "$PAGE_CNN_PIXPARSE_LIMIT"
fi

AKDENIZ_GT="${PAGE_CNN_AKDENIZ_GT:-$ROOT/data/akdeniz-gt}"
if [[ -d "$AKDENIZ_GT/kraken-vatlib-gt" ]]; then
  python scripts/fetch_page_cnn_data.py \
    --out "$DATA" \
    --extra "manuscript:$AKDENIZ_GT/kraken-vatlib-gt"
fi

N_MS=$(find "$DATA/manuscript" -type f 2>/dev/null | wc -l)
if [[ "$N_MS" -lt 4 ]]; then
  echo "[fetch] manuscript=$N_MS — bootstrapping IIIF seeds"
  python scripts/bootstrap_page_cnn_data.py --out "$DATA"
fi

python scripts/fetch_page_cnn_data.py --list || true
echo "[fetch] print=$(find "$DATA/print" -type f 2>/dev/null | wc -l) manuscript=$(find "$DATA/manuscript" -type f 2>/dev/null | wc -l)"
