#!/usr/bin/env bash
# Load Python >= 3.11 on Bridges2 (login or compute nodes).
# Default `module load python` is 3.8.6 — use Anaconda 3.12.
set -euo pipefail

module purge 2>/dev/null || true

if module load anaconda3/2024.10-1 2>/dev/null; then
  :
elif module load anaconda3 2>/dev/null; then
  :
else
  echo "ERROR: could not load anaconda3 (need Python >= 3.11 on Bridges)" >&2
  echo "  module avail anaconda3" >&2
  exit 1
fi

BRIDGES_PYTHON3="$(command -v python3)"
if ! "$BRIDGES_PYTHON3" -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "ERROR: need Python >= 3.11; got $("$BRIDGES_PYTHON3" --version 2>&1) at $BRIDGES_PYTHON3" >&2
  exit 1
fi

export BRIDGES_PYTHON3
export PATH="$(dirname "$BRIDGES_PYTHON3"):${PATH:-}"
