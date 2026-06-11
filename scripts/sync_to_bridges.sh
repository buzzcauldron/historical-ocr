#!/usr/bin/env bash
# Sync historical-ocr to Bridges2 (run from your Mac).
set -euo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
REMOTE="${BRIDGES_DTN:-bridges2-dtn}"
DEST="${BRIDGES_HISTORICAL_OCR:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"

rsync -avz --delete \
  -e "ssh -o BatchMode=yes" \
  --exclude '.venv/' \
  --exclude 'jobs/' \
  --exclude 'data/' \
  --exclude '/models/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.egg-info/' \
  "$REPO/" "${REMOTE}:${DEST}/"

echo "[sync] -> ${REMOTE}:${DEST}"
