#!/usr/bin/env bash
# Rsync Akdeniz manuscript GT page images to Bridges2 for page-CNN training.
# Run on Akdeniz (mirrors transcription-shell xfer_akdeniz_gt_to_bridges.sh).
#
# Usage:
#   bash scripts/xfer_akdeniz_page_cnn_to_bridges.sh
#   bash scripts/xfer_akdeniz_page_cnn_to_bridges.sh --dry-run

set -euo pipefail

BRIDGES_GT="${BRIDGES_PAGE_CNN_GT:-/ocean/projects/hum260002p/sstrickland/historical-ocr/data/akdeniz-gt}"
BRIDGES_HOST="${BRIDGES_HOST:-bridges2-dtn}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

ensure_remote_base() {
  echo "[akdeniz-page-cnn] ensuring remote: ${BRIDGES_HOST}:${BRIDGES_GT}"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  ssh -o StrictHostKeyChecking=accept-new "$BRIDGES_HOST" "mkdir -p '${BRIDGES_GT}'"
}

xfer_dir() {
  local src="$1" name="$2"
  local -a rsync_cmd=(
    rsync -avh --partial --append-verify --info=progress2
    --exclude='.git/'
    --include='*/' --include='*.jpg' --include='*.jpeg' --include='*.png'
    --include='*.tif' --include='*.tiff' --include='*.bmp' --exclude='*'
    -e "ssh -o StrictHostKeyChecking=accept-new"
  )
  [[ -d "$src" ]] || { echo "[skip] $src"; return 0; }
  echo "[xfer] $src -> ${BRIDGES_GT}/${name}/"
  if [[ "$DRY_RUN" == "1" ]]; then
    "${rsync_cmd[@]}" -n "$src/" "${BRIDGES_HOST}:${BRIDGES_GT}/${name}/"
  else
    "${rsync_cmd[@]}" "$src/" "${BRIDGES_HOST}:${BRIDGES_GT}/${name}/"
  fi
}

echo "[akdeniz-page-cnn] $(date -Iseconds) -> $BRIDGES_GT"
ensure_remote_base

xfer_dir "$HOME/kraken-vatlib-gt"     kraken-vatlib-gt
xfer_dir "$HOME/kraken-cp40-gt"       kraken-cp40-gt
xfer_dir "$HOME/kraken-done-lines-gt" kraken-done-lines-gt
xfer_dir "$HOME/deed-finetune-gt"     deed-finetune-gt
xfer_dir "$HOME/src/deed-finetune-gt" deed-finetune-gt-src
xfer_dir "$HOME/src/kraken-vatlib-gt" kraken-vatlib-gt-src

echo "[akdeniz-page-cnn] done — on Bridges: sbatch scripts/bridges_train_page_cnn.sbatch"
