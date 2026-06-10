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

DOC_TXT="$ROOT/jobs/$JOB/export/document.txt"
DOC_XML="$ROOT/jobs/$JOB/export/document.xml"
DELIVERY="$ROOT/jobs/$JOB/export/delivery.json"
fail=0

if [[ ! -f "$DOC_TXT" ]]; then
  echo "FAIL: missing export/document.txt"
  fail=1
fi
if [[ ! -f "$DOC_XML" ]]; then
  echo "FAIL: missing export/document.xml"
  fail=1
fi
if [[ ! -f "$DELIVERY" ]]; then
  echo "FAIL: missing export/delivery.json"
  fail=1
fi

if [[ -f "$DOC_TXT" ]]; then
  echo "  document.txt: $DOC_TXT ($(wc -c <"$DOC_TXT") bytes)"
fi
if [[ -f "$DOC_XML" ]]; then
  echo "  document.xml: $DOC_XML ($(wc -c <"$DOC_XML") bytes)"
  head -n 3 "$DOC_XML"
fi

if command -v ocr-cleanup >/dev/null 2>&1; then
  echo ""
  echo "=== print OCR + Underwood clean ==="
  JOB2="versions-clean"
  rm -rf "$ROOT/jobs/$JOB2"
  historical-ocr run "$JOB2" -i "$PDF" --mode print --clean
  shopt -s nullglob
  c_doc="$ROOT/jobs/$JOB2/export/document.txt"
  c_raw=("$ROOT/jobs/$JOB2/clean"/*.txt)
  shopt -u nullglob
  if [[ ! -f "$c_doc" ]]; then
    echo "FAIL: clean job missing export/document.txt"
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
echo "OK: document.txt + document.xml verified"
