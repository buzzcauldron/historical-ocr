#!/bin/bash
#SBATCH -J tess-train-fetch
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 24:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
# Fetch HF newspaper OCR corpora + prepare tesstrain line GT on Bridges2.
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${TESS_TRAIN_DATA:-$ROOT/data/tesseract_train}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"
mkdir -p "$DATA"

TESSTRAIN="${TESS_TRAIN_REPO:-$DATA/tesstrain_repo}"
if [[ ! -f "$TESSTRAIN/Makefile" ]]; then
  echo "[fetch] clone tesstrain → $TESSTRAIN"
  git clone --depth 1 https://github.com/tesseract-ocr/tesstrain.git "$TESSTRAIN"
fi

TESSDATA="${TESS_TRAIN_TESSDATA:-$DATA/tessdata_best}"
mkdir -p "$TESSDATA"
if [[ ! -f "$TESSDATA/eng.traineddata" ]]; then
  echo "[fetch] download tessdata_best eng.traineddata"
  curl -fsSL -o "$TESSDATA/eng.traineddata" \
    "https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata"
fi

LIMIT_ARGS=()
if [[ -n "${TESS_TRAIN_LIMIT:-}" ]]; then
  LIMIT_ARGS=(--limit "$TESS_TRAIN_LIMIT")
fi

LOCAL_ARGS=()
if [[ -n "${TESS_TRAIN_LOCAL:-}" ]]; then
  IFS=',' read -ra _locals <<< "$TESS_TRAIN_LOCAL"
  for lid in "${_locals[@]}"; do
    LOCAL_ARGS+=(--local "$lid")
  done
fi

SOURCE_ARGS=()
if [[ -n "${TESS_TRAIN_SOURCES:-}" ]]; then
  IFS=',' read -ra _sources <<< "$TESS_TRAIN_SOURCES"
  for sid in "${_sources[@]}"; do
    SOURCE_ARGS+=(--source "$sid")
  done
fi

# Default sources when TESS_TRAIN_SOURCES is unset: all four newspaper corpora.
# chronicling-america + newspaper-ocr-gold cover 19th-c; 1920s extends to mid-20th-c.
if [[ -z "${TESS_TRAIN_SOURCES:-}" ]]; then
  SOURCE_ARGS=(
    --source chronicling-america
    --source newspaper-ocr-gold
    --source chronicling-america-1920s
    --source ocr-quality
  )
fi

# Always include local newspaper_gt (train split only — val is held out for gt eval).
LOCAL_ARGS+=(--local newspaper_gt)

historical-ocr tess fetch \
  --out "$DATA" \
  "${SOURCE_ARGS[@]}" \
  "${LOCAL_ARGS[@]}" \
  "${LIMIT_ARGS[@]}"

historical-ocr tess prepare --corpus "$DATA"

N_PAGES=$(find "$DATA/pages" -name '*.json' 2>/dev/null | wc -l)
N_LINES=$(find "$DATA/tesstrain" -name '*.png' 2>/dev/null | wc -l)
echo "[fetch] pages=$N_PAGES line_pairs=$N_LINES corpus=$DATA"
