#!/bin/bash
#SBATCH -J newspaper-gt-fetch
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 04:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
OUT="${NEWSPAPER_GT_DIR:-$ROOT/data/newspaper_gt}"
LIMIT="${NEWSPAPER_GT_LIMIT:-2000}"
VAL_RATIO="${NEWSPAPER_GT_VAL_RATIO:-0.1}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"

python scripts/fetch_newspaper_gt.py \
  --out "$OUT" \
  --limit "$LIMIT" \
  --val-ratio "$VAL_RATIO"

python scripts/prepare_newspaper_ocr.py --out "${NEWSPAPER_OCR_DIR:-$ROOT/data/newspaper_ocr}"
echo "done fetch+prepare"
