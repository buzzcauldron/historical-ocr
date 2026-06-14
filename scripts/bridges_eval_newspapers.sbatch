#!/bin/bash
#SBATCH -J np-eval
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 01:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
# Evaluate OCR quality on held-out newspaper_gt val split.
# Run after any training job to track CER improvement.
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"
SPLIT="${EVAL_SPLIT:-val}"
PRESET="${EVAL_PRESET:-medium}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$ROOT"

STAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT_DIR="$ROOT/data/newspaper_gt/eval/eval_${PRESET}_${STAMP}"

echo "[eval] split=$SPLIT preset=$PRESET"
historical-ocr gt eval \
  --gt-dir "$ROOT/data/newspaper_gt" \
  --split "$SPLIT" \
  --preset "$PRESET" \
  --out "$OUT_DIR"

echo "[eval] results at $OUT_DIR/report.json"
python3 -c "
import json, pathlib
r = json.loads(pathlib.Path('$OUT_DIR/report.json').read_text())
print(f'mean CER: {r[\"mean_cer\"]:.4f}  mean WER: {r[\"mean_wer\"]:.4f}  ({r[\"scored\"]} pages)')
for p in r.get('pages', []):
    print(f'  {p[\"record_id\"]}: CER {p[\"cer\"]:.4f}')
"
