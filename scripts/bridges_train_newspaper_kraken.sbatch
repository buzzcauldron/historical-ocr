#!/bin/bash
#SBATCH -J kraken-news
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 12:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
# Train a Kraken HTR model on newspaper line-pair GT.
# Must run after bridges_fetch_tesseract_train.sbatch (which produces line pairs).
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
TESS_DATA="${TESS_TRAIN_DATA:-$ROOT/data/tesseract_train}"
KRAKEN_GT="${KRAKEN_GT_DIR:-$ROOT/data/kraken_gt}"
OUT="${KRAKEN_MODEL:-$ROOT/models/newspaper_kraken}"
EPOCHS="${KRAKEN_EPOCHS:-40}"
BATCH="${KRAKEN_BATCH:-16}"
LAG="${KRAKEN_LAG:-5}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"
mkdir -p "$(dirname "$OUT")"

if ! command -v ketos >/dev/null 2>&1; then
  pip install -q 'kraken>=5.0'
fi

TESSTRAIN_GT="${TESS_DATA}/tesstrain/histnews-ground-truth"
N_LINES=$(find "$TESSTRAIN_GT" -name '*.png' 2>/dev/null | wc -l)
echo "[kraken] found $N_LINES line pairs in $TESSTRAIN_GT"
if [[ "$N_LINES" -lt 100 ]]; then
  echo "ERROR: need at least 100 line pairs; run bridges_fetch_tesseract_train first" >&2
  exit 1
fi

# Build train/eval manifests, holding out newspaper_gt val pages.
python scripts/build_kraken_gt.py \
  --gt-dir "$TESSTRAIN_GT" \
  --val-manifest "$ROOT/data/newspaper_gt/manifest.json" \
  --out "$KRAKEN_GT"

N_TRAIN=$(wc -l < "$KRAKEN_GT/train.txt")
N_EVAL=$(wc -l < "$KRAKEN_GT/eval.txt")
echo "[kraken] training on $N_TRAIN lines, eval on $N_EVAL lines"

# Train Kraken model.
ketos \
  --device cuda \
  --workers 4 \
  train \
  --output "$OUT" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH" \
  --quit early \
  --lag "$LAG" \
  --evaluation-data "$KRAKEN_GT/eval.txt" \
  $(cat "$KRAKEN_GT/train.txt")

echo "[kraken] model saved to ${OUT}_best.mlmodel (or similar)"

# Post-training evaluation against held-out newspaper_gt val pages.
echo "[eval] running gt eval on held-out newspaper_gt val split"
historical-ocr gt eval \
  --gt-dir "$ROOT/data/newspaper_gt" \
  --split val \
  --preset medium \
  --out "$ROOT/data/newspaper_gt/eval/kraken_post_train_$(date -u +%Y-%m-%dT%H-%M-%SZ)"

echo "[kraken] done"
