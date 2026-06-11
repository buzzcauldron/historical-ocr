#!/usr/bin/env bash
# Create historical-ocr venv on Bridges2 login node.
#
#   cd /ocean/projects/hum260002p/sstrickland/historical-ocr
#   bash scripts/setup_bridges_venv.sh
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

export PYTHONNOUSERSITE=True
# Lmod needs a login shell on some SSH sessions; preload before bridges_load_python.
module purge 2>/dev/null || true
module load anaconda3/2024.10-1 2>/dev/null || module load anaconda3 2>/dev/null || true
# shellcheck disable=SC1091
source "$(dirname "$0")/bridges_load_python.sh"

echo "[venv] python: $(which python3) ($(python3 --version))"
echo "[venv] target: $VENV"

if [[ -d "$VENV" ]]; then
  if ! "$VENV/bin/python" -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    echo "[venv] removing stale venv (wrong Python version)"
    rm -rf "$VENV"
  elif ! "$VENV/bin/python" -c "import sys" 2>/dev/null; then
    rm -rf "$VENV"
  fi
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  "${BRIDGES_PYTHON3:-python3}" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install -U pip setuptools wheel
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -e "$ROOT[figures]"

python -c "import torch; from historical_ocr.ml.page_cnn import torch_available; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'ml', torch_available())"
historical-ocr --version

echo "[venv] ready: source $VENV/bin/activate"
