#!/usr/bin/env bash
# Run print + (optional) clean pipeline and assert export/txt + export/xml exist.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

JOB="versions-smoke"
PDF="$ROOT/tests/fixtures/sample_print.pdf"

if [[ ! -f "$PDF" ]]; then
  python3 -c "
import fitz
from pathlib import Path
p = Path('$PDF')
p.parent.mkdir(parents=True, exist_ok=True)
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), 'The king-dom of England was united.', fontsize=14)
doc.save(str(p))
doc.close()
"
fi

rm -rf "$ROOT/jobs/$JOB"

echo "=== print OCR (no clean) ==="
historical-ocr run "$JOB" -i "$PDF" --mode print --no-clean

TXT_DIR="$ROOT/jobs/$JOB/export/txt"
XML_DIR="$ROOT/jobs/$JOB/export/xml"
fail=0

shopt -s nullglob
txts=("$TXT_DIR"/*.txt)
xmls=("$XML_DIR"/*.xml)
shopt -u nullglob

if [[ ${#txts[@]} -lt 1 ]]; then
  echo "FAIL: no export/txt/*.txt"
  fail=1
fi
if [[ ${#xmls[@]} -lt 1 ]]; then
  echo "FAIL: no export/xml/*.xml"
  fail=1
fi

for f in "${txts[@]}"; do
  echo "  txt: $f ($(wc -c <"$f") bytes)"
done
for f in "${xmls[@]}"; do
  echo "  xml: $f ($(wc -c <"$f") bytes)"
  head -n 3 "$f"
done

if command -v ocr-cleanup >/dev/null 2>&1; then
  echo ""
  echo "=== print OCR + Underwood clean ==="
  JOB2="versions-clean"
  rm -rf "$ROOT/jobs/$JOB2"
  historical-ocr run "$JOB2" -i "$PDF" --mode print --clean
  shopt -s nullglob
  c_txts=("$ROOT/jobs/$JOB2/export/txt"/*.txt)
  c_raw=("$ROOT/jobs/$JOB2/clean"/*.txt)
  shopt -u nullglob
  if [[ ${#c_txts[@]} -lt 1 ]]; then
    echo "FAIL: clean job missing export/txt"
    fail=1
  fi
  if [[ ${#c_raw[@]} -lt 1 ]]; then
    echo "FAIL: clean job missing clean/*.txt"
    fail=1
  fi
  echo "  clean pass OK"
fi

historical-ocr tools

if [[ $fail -ne 0 ]]; then
  exit 1
fi
echo "OK: txt + xml outputs verified"
