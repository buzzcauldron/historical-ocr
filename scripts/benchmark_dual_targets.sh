#!/usr/bin/env bash
# Benchmark both newspaper targets (LLM-independent):
#   1. Chronicling America GT — gt fetch + gt eval (CER/WER vs LOC text)
#   2. Black News 1970 — rules-only OCR regression snapshot (no public GT)
#
# Usage:
#   bash scripts/benchmark_dual_targets.sh
#   GT_LIMIT=500 VAL_LIMIT=50 bash scripts/benchmark_dual_targets.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

PYTHON="${REPO}/.venv/bin/python"
HOCR="${REPO}/.venv/bin/historical-ocr"
GT_DIR="${GT_DIR:-data/newspaper_gt}"
GT_LIMIT="${GT_LIMIT:-200}"
VAL_RATIO="${VAL_RATIO:-0.1}"
VAL_LIMIT="${VAL_LIMIT:-20}"
BLACKNEWS_TIF="${BLACKNEWS_TIF:-$HOME/Downloads/BlackNews_19700110_002.tif}"
BENCH_DIR="${BENCH_DIR:-data/benchmarks}"

if [[ ! -x "$HOCR" ]]; then
  echo "error: run pip install -e . first" >&2
  exit 1
fi

mkdir -p "$BENCH_DIR"

echo "=== [1/3] Chronicling America GT fetch (limit=${GT_LIMIT}) ==="
"$PYTHON" scripts/fetch_newspaper_gt.py \
  --out "$GT_DIR" \
  --limit "$GT_LIMIT" \
  --val-ratio "$VAL_RATIO"

echo ""
echo "=== [2/3] CA validation eval (limit=${VAL_LIMIT}, rules-only) ==="
"$HOCR" gt eval --gt-dir "$GT_DIR" --split val --limit "$VAL_LIMIT"

echo ""
echo "=== [3/3] Black News 1970 regression snapshot ==="
if [[ ! -f "$BLACKNEWS_TIF" ]]; then
  echo "skip: BlackNews TIFF not found at $BLACKNEWS_TIF" >&2
else
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT="${BENCH_DIR}/blacknews_${STAMP}"
  mkdir -p "$OUT"
  /usr/bin/time -p "$HOCR" run "_bench_blacknews" \
    -i "$BLACKNEWS_TIF" \
    --mode print \
    --publication-year 1970 \
    --low-latency 2>&1 | tee "$OUT/run.log"
  JOB="${REPO}/jobs/_bench_blacknews/export"
  cp "$JOB/BlackNews_19700110_002.txt" "$OUT/" 2>/dev/null || true
  cp "$JOB/BlackNews_19700110_002.review.json" "$OUT/" 2>/dev/null || true
  ln -sfn "$OUT" "${BENCH_DIR}/blacknews_latest"
  echo "blacknews snapshot → $OUT"
  rm -rf "${REPO}/jobs/_bench_blacknews"
fi

echo ""
echo "done."
echo "  CA corpus:    $GT_DIR"
echo "  CA eval:      $GT_DIR/eval/"
echo "  Black News:   ${BENCH_DIR}/blacknews_latest"
