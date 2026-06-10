#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="$(cd "$ROOT/.." && pwd)"
VENV="$ROOT/.venv"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip
pip install -e "$ROOT[all]"

# Optional siblings (not required for core install)
if [[ -d "$PROJECTS/ocr-cleanup" ]]; then
  echo "→ editable: ocr-cleanup (Ted Underwood rules)"
  pip install -e "$PROJECTS/ocr-cleanup"
else
  echo "→ note: ../ocr-cleanup not found — print --clean will be skipped"
  echo "  Clone DataMunging fork or: git clone <ocr-cleanup-url> $PROJECTS/ocr-cleanup"
fi

[[ -f "$ROOT/.env" ]] || cp "$ROOT/.env.example" "$ROOT/.env"

echo ""
echo "Done. Activate: source $VENV/bin/activate"
historical-ocr --version
historical-ocr tools
