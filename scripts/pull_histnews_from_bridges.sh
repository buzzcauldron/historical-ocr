#!/usr/bin/env bash
# Pull trained histnews.traineddata from Bridges2 to local models/.
#
#   bash scripts/pull_histnews_from_bridges.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${BRIDGES_DTN:-bridges2-dtn}"
SRC="${BRIDGES_HISTNEWS_MODEL:-/ocean/projects/hum260002p/sstrickland/historical-ocr/models/histnews.traineddata}"
DEST="${REPO}/models/histnews.traineddata"

mkdir -p "$(dirname "$DEST")"
scp -o BatchMode=yes "${REMOTE}:${SRC}" "${DEST}"
echo "[pull] ${DEST} ($(wc -c < "$DEST") bytes)"
# Re-run blind OCR compare when ready:
echo "  .venv/bin/python scripts/blind_model_eval.py"
