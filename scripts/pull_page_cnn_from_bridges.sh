#!/usr/bin/env bash
# Pull trained page-CNN checkpoint from Bridges2 to local models/.
#
#   bash scripts/pull_page_cnn_from_bridges.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${BRIDGES_DTN:-bridges2-dtn}"
SRC="${BRIDGES_PAGE_CNN_MODEL:-/ocean/projects/hum260002p/sstrickland/historical-ocr/models/page_cnn.pt}"
DEST="${REPO}/models/page_cnn.pt"

mkdir -p "$(dirname "$DEST")"
scp -o BatchMode=yes "${REMOTE}:${SRC}" "${DEST}"
echo "[pull] ${DEST}"
python3 -c "
import torch
from pathlib import Path
p = Path('${DEST}')
d = torch.load(p, map_location='cpu', weights_only=False)
print('val_acc=', d.get('val_accuracy'), 'train=', d.get('train_count'), 'epochs=', d.get('epochs_run'))
"
