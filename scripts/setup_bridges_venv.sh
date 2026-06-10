#!/usr/bin/env bash
# Create historical-ocr venv on Bridges2 login node.
#
#   cd /ocean/projects/hum260002p/sstrickland/historical-ocr
#   bash scripts/setup_bridges_venv.sh
set -euo pipefail

ROOT="${HISTORICAL_OCR_ROOT:-/ocean/projects/hum260002p/sstrickland/historical-ocr}"
VENV="${HISTORICAL_OCR_VENV:-$ROOT/.venv}"

export PYTHONNOUSERSITE=True
# historical-ocr requires Python >= 3.11; default `module load python` on Bridges is 3.8.
for mod in python3.11 python/3.11 python3 python anaconda3; do
  module load "$mod" 2>/dev/null || true
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    break
  fi
done

if ! command -v python3 >/dev/null; then
  echo "ERROR: load Python >= 3.11 (e.g. module load python3.11)" >&2
  exit 1
fi
if ! python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "ERROR: need Python >= 3.11; got $(python3 --version)" >&2
  exit 1
fi

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
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install -U pip setuptools wheel
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -e "$ROOT[ml,pdf,print]"

python -c "import torch; from historical_ocr.ml.page_cnn import torch_available; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'ml', torch_available())"
historical-ocr --version

echo "[venv] ready: source $VENV/bin/activate"
