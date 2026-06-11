#!/usr/bin/env bash
# Sync repo and submit Tesseract fine-tune fetch → train on Bridges2.
#
#   bash scripts/submit_bridges_tesseract_train.sh
#   bash scripts/submit_bridges_tesseract_train.sh --fetch-only
#   bash scripts/submit_bridges_tesseract_train.sh --train-only
#
# Optional env:
#   TESS_TRAIN_LIMIT=3000
#   TESS_TRAIN_SOURCES=chronicling-america,newspaper-ocr-gold,ocr-quality
#   TESS_TRAIN_LOCAL=newspaper_gt,user_gt
#   TESS_TRAIN_MAX_ITER=10000
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DTN="${BRIDGES_DTN:-bridges2-dtn}"
LOGIN="${BRIDGES_LOGIN:-bridges2}"
DEST="${BRIDGES_HISTORICAL_OCR:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"

FETCH_ONLY=0
TRAIN_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --fetch-only) FETCH_ONLY=1 ;;
    --train-only) TRAIN_ONLY=1 ;;
  esac
done

echo "[bridges] sync $REPO -> $DTN:$DEST"
bash "$REPO/scripts/sync_to_bridges.sh"

echo "[bridges] verify venv"
ssh -o BatchMode=yes "$LOGIN" "bash -lc 'cd \"$DEST\" && source .venv/bin/activate && historical-ocr --version && tesseract --version 2>/dev/null | head -1 || echo tesseract-missing'"

REMOTE_ENV="cd '$DEST'"
[[ -n "${TESS_TRAIN_LIMIT:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export TESS_TRAIN_LIMIT='$TESS_TRAIN_LIMIT'"
[[ -n "${TESS_TRAIN_SOURCES:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export TESS_TRAIN_SOURCES='$TESS_TRAIN_SOURCES'"
[[ -n "${TESS_TRAIN_LOCAL:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export TESS_TRAIN_LOCAL='$TESS_TRAIN_LOCAL'"
[[ -n "${TESS_TRAIN_MAX_ITER:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export TESS_TRAIN_MAX_ITER='$TESS_TRAIN_MAX_ITER'"

if [[ "$TRAIN_ONLY" -eq 0 ]]; then
  echo "[bridges] submit tess fetch job (GPU-shared, up to 12h)"
  FETCH_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable scripts/bridges_fetch_tesseract_train.sbatch'")
  echo "[bridges] fetch job: $FETCH_JOB"
fi

if [[ "$FETCH_ONLY" -eq 1 ]]; then
  echo "[bridges] fetch-only — monitor: ssh $LOGIN tail -f $DEST/tess-train-fetch-*.out"
  exit 0
fi

if [[ "$TRAIN_ONLY" -eq 1 ]]; then
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable scripts/bridges_train_tesseract.sbatch'")
else
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable --dependency=afterok:$FETCH_JOB scripts/bridges_train_tesseract.sbatch'")
fi

echo "[bridges] train job: $TRAIN_JOB"
echo ""
echo "Monitor:"
echo "  ssh $LOGIN squeue -u \$USER"
echo "  ssh $LOGIN tail -f $DEST/tess-train-fetch-*.out $DEST/tess-train-*.out"
echo ""
echo "Pull model when done:"
echo "  scp $DTN:$DEST/models/histnews.traineddata $REPO/models/"
