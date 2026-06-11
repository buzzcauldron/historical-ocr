#!/bin/bash
#SBATCH -J page-cnn-train
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:v100-32:1
#SBATCH -N 1
#SBATCH --ntasks-per-node=5
#SBATCH -t 02:00:00
#SBATCH -A hum260002p
#SBATCH -o %x-%j.out
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
DATA="${PAGE_CNN_DATA:-$ROOT/data/page_cnn}"
OUT="${PAGE_CNN_MODEL:-$ROOT/models/page_cnn.pt}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

# shellcheck disable=SC1091
source "$ROOT/scripts/bridges_load_python.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$ROOT"
mkdir -p "$(dirname "$OUT")"

python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

N_PRINT=$(find "$DATA/print" -type f 2>/dev/null | wc -l)
N_MS=$(find "$DATA/manuscript" -type f 2>/dev/null | wc -l)
echo "[train] dataset: $N_PRINT print, $N_MS manuscript"
if [[ "$N_PRINT" -lt 4 || "$N_MS" -lt 4 ]]; then
  echo "ERROR: need at least 4 images per class under $DATA/{print,manuscript}/" >&2
  echo "Run bridges_fetch_page_cnn.sbatch first (and Akdeniz xfer for manuscript)." >&2
  exit 1
fi

historical-ocr cnn train \
  --data "$DATA" \
  --out "$OUT" \
  --epochs "${PAGE_CNN_EPOCHS:-25}" \
  --patience "${PAGE_CNN_PATIENCE:-3}" \
  --batch-size "${PAGE_CNN_BATCH:-32}" \
  --image-size "${PAGE_CNN_SIZE:-224}"

python -c "
import torch
from pathlib import Path
p=Path('$OUT')
d=torch.load(p,map_location='cpu',weights_only=False)
print('saved', p, 'val_acc=', d.get('val_accuracy'), 'train=', d.get('train_count'), 'val=', d.get('val_count'))
"
