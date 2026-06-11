#!/usr/bin/env bash
# Sync repo and submit newspaper GT fetch → Kraken train on Bridges2.
#
#   bash scripts/submit_bridges_newspaper_ocr.sh
#   NEWSPAPER_GT_LIMIT=500 bash scripts/submit_bridges_newspaper_ocr.sh --fetch-only
#   bash scripts/submit_bridges_newspaper_ocr.sh --train-only
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
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

bash "$REPO/scripts/sync_to_bridges.sh"
ssh -o BatchMode=yes "$LOGIN" "bash -lc 'cd \"$DEST\" && bash scripts/setup_bridges_venv.sh'"

REMOTE="cd '$DEST'"
[[ -n "${NEWSPAPER_GT_LIMIT:-}" ]] && REMOTE="$REMOTE && export NEWSPAPER_GT_LIMIT='$NEWSPAPER_GT_LIMIT'"
[[ -n "${NEWSPAPER_OCR_EPOCHS:-}" ]] && REMOTE="$REMOTE && export NEWSPAPER_OCR_EPOCHS='$NEWSPAPER_OCR_EPOCHS'"

if [[ "$TRAIN_ONLY" -eq 0 ]]; then
  FETCH_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE && sbatch --parsable scripts/bridges_fetch_newspaper_gt.sbatch'")
  echo "[bridges] fetch+prepare job: $FETCH_JOB"
fi

if [[ "$FETCH_ONLY" -eq 1 ]]; then
  exit 0
fi

if [[ "$TRAIN_ONLY" -eq 1 ]]; then
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE && sbatch --parsable scripts/bridges_train_newspaper_ocr.sbatch'")
else
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE && sbatch --parsable --dependency=afterok:$FETCH_JOB scripts/bridges_train_newspaper_ocr.sbatch'")
fi
echo "[bridges] train job: $TRAIN_JOB"
