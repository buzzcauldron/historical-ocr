#!/bin/bash
#SBATCH -J newspaper-ocr-train
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 08:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${NEWSPAPER_OCR_DIR:-$ROOT/data/newspaper_ocr}"
OUT="${NEWSPAPER_OCR_MODEL:-$ROOT/models/newspaper_ocr.mlmodel}"
EPOCHS="${NEWSPAPER_OCR_EPOCHS:-30}"
BATCH="${NEWSPAPER_OCR_BATCH:-8}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

mkdir -p "$ROOT/logs"
exec > >(tee -a "$ROOT/logs/newspaper-ocr-train-${SLURM_JOB_ID:-local}.log") 2>&1

if ! command -v tesseract >/dev/null 2>&1; then
  echo "ERROR: tesseract not on PATH — load module or install on compute node" >&2
  exit 1
fi
echo "[train] tesseract: $(tesseract --version 2>&1 | head -1)"
echo "[train] langs: $(tesseract --list-langs 2>&1 | tr '\n' ' ')"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"
mkdir -p "$(dirname "$OUT")"

if ! command -v ketos >/dev/null 2>&1; then
  echo "[train] installing kraken into venv"
  pip install -q 'kraken>=5.0'
fi

python scripts/prepare_newspaper_ocr.py --out "$DATA"
historical-ocr newspaper train --data "$DATA" --out "$OUT" --epochs "$EPOCHS" --batch-size "$BATCH"
echo "saved $OUT"
