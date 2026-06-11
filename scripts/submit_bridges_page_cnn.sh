#!/usr/bin/env bash
# From your Mac: sync repo, ensure venv, submit fetch → train on Bridges2.
#
#   bash scripts/submit_bridges_page_cnn.sh
#   bash scripts/submit_bridges_page_cnn.sh --fetch-only
#   bash scripts/submit_bridges_page_cnn.sh --train-only
#
# Optional env:
#   PAGE_CNN_LIMIT=2000          cap per HF source
#   PAGE_CNN_PIXPARSE_LIMIT=500  add pixparse sample
#   NEWSPAPER_GT_LIMIT=2000      Chronicling America pages → print class
#   PAGE_CNN_EPOCHS=25
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

echo "[bridges] setup venv on login node (idempotent)"
ssh -o BatchMode=yes "$LOGIN" "bash -lc 'cd \"$DEST\" && bash scripts/setup_bridges_venv.sh'"

echo "[bridges] verify venv"
ssh -o BatchMode=yes "$LOGIN" "bash -lc 'cd \"$DEST\" && source .venv/bin/activate && historical-ocr --version && python -c \"import torch; print(torch.__version__)\"'"

REMOTE_ENV="cd '$DEST'"
[[ -n "${PAGE_CNN_LIMIT:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export PAGE_CNN_LIMIT='$PAGE_CNN_LIMIT'"
[[ -n "${PAGE_CNN_PIXPARSE_LIMIT:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export PAGE_CNN_PIXPARSE_LIMIT='$PAGE_CNN_PIXPARSE_LIMIT'"
[[ -n "${PAGE_CNN_EPOCHS:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export PAGE_CNN_EPOCHS='$PAGE_CNN_EPOCHS'"
[[ -n "${NEWSPAPER_GT_LIMIT:-}" ]] && REMOTE_ENV="$REMOTE_ENV && export NEWSPAPER_GT_LIMIT='$NEWSPAPER_GT_LIMIT'"

if [[ "$TRAIN_ONLY" -eq 0 ]]; then
  echo "[bridges] submit fetch job (RM-shared, up to 6h)"
  FETCH_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable scripts/bridges_fetch_page_cnn.sbatch'")
  echo "[bridges] fetch job: $FETCH_JOB"
fi

if [[ "$FETCH_ONLY" -eq 1 ]]; then
  echo "[bridges] fetch-only — monitor: ssh $LOGIN \"squeue -u \\\$USER\"; tail -f $DEST/page-cnn-fetch-${FETCH_JOB:-*}.out\""
  exit 0
fi

if [[ "$TRAIN_ONLY" -eq 1 ]]; then
  echo "[bridges] submit train job (no fetch dependency)"
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable scripts/bridges_train_page_cnn.sbatch'")
else
  echo "[bridges] submit train job after fetch completes"
  TRAIN_JOB=$(ssh -o BatchMode=yes "$LOGIN" "bash -lc '$REMOTE_ENV && sbatch --parsable --dependency=afterok:$FETCH_JOB scripts/bridges_train_page_cnn.sbatch'")
fi

if [[ "$TRAIN_ONLY" -eq 0 && -z "${FETCH_JOB:-}" ]]; then
  echo "[bridges] ERROR: fetch sbatch returned empty job id" >&2
  exit 1
fi
if [[ "$FETCH_ONLY" -eq 0 && -z "${TRAIN_JOB:-}" ]]; then
  echo "[bridges] ERROR: train sbatch returned empty job id" >&2
  exit 1
fi

echo "[bridges] train job: $TRAIN_JOB"
echo ""
echo "Monitor:"
echo "  ssh $LOGIN squeue -u \$USER"
echo "  ssh $LOGIN tail -f $DEST/page-cnn-fetch-*.out $DEST/page-cnn-train-*.out"
echo ""
echo "Pull model when done:"
echo "  scp $DTN:$DEST/models/page_cnn.pt $REPO/models/"
