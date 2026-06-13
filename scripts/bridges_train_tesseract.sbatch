#!/bin/bash
#SBATCH -J tess-train
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 24:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
# Fine-tune Tesseract LSTM (histnews) via tesstrain on Bridges2.
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${TESS_TRAIN_DATA:-$ROOT/data/tesseract_train}"
OUT="${TESS_TRAIN_MODEL:-$ROOT/models/histnews.traineddata}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"
mkdir -p "$(dirname "$OUT")"

N_LINES=$(find "$DATA/tesstrain" -name '*.png' 2>/dev/null | wc -l)
echo "[train] line_pairs=$N_LINES data=$DATA"
if [[ "$N_LINES" -lt 100 ]]; then
  echo "ERROR: need >= 100 line pairs — run bridges_fetch_tesseract_train.sbatch first" >&2
  exit 1
fi

TRAIN_ARGS=()
if [[ -n "${TESS_TRAIN_MAX_ITER:-}" ]]; then
  TRAIN_ARGS+=(--max-iterations "$TESS_TRAIN_MAX_ITER")
fi
if [[ -n "${TESS_TRAIN_MODEL_NAME:-}" ]]; then
  TRAIN_ARGS+=(--model "$TESS_TRAIN_MODEL_NAME")
fi

historical-ocr tess train \
  --data "$DATA" \
  --out "$OUT" \
  "${TRAIN_ARGS[@]}"

TESSDATA_DIR="${TESS_TRAIN_TESSDATA_PREFIX:-$ROOT/models/tessdata}"
mkdir -p "$TESSDATA_DIR"
SRC_BEST="${TESS_TRAIN_TESSDATA:-$DATA/tessdata_best}"
if [[ -f "$SRC_BEST/eng.traineddata" && ! -f "$TESSDATA_DIR/eng.traineddata" ]]; then
  cp "$SRC_BEST/eng.traineddata" "$TESSDATA_DIR/"
fi
cp "$OUT" "$TESSDATA_DIR/$(basename "$OUT")"

export TESSDATA_PREFIX="$TESSDATA_DIR"
tesseract --list-langs 2>/dev/null | head -20 || true
echo "[train] saved $OUT tessdata_prefix=$TESSDATA_DIR"

# Run post-training CER eval on held-out newspaper_gt val split.
echo "[eval] evaluating on newspaper_gt val split"
STAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
historical-ocr gt eval \
  --gt-dir "$ROOT/data/newspaper_gt" \
  --split val \
  --preset medium \
  --out "$ROOT/data/newspaper_gt/eval/tess_post_train_${STAMP}" \
  || echo "[eval] WARNING: gt eval failed (non-fatal)"
