# Newspaper OCR training

Train a **Kraken** page OCR model from Chronicling America GT + your corrected text.

## Data sources

| Corpus | Path | Text |
|--------|------|------|
| Chronicling America | `data/newspaper_gt/` | LOC `ocr_text` (1770–1810) |
| Your corrections | `data/user_gt/` | Human-edited `.corrected.txt` via `gt submit` |
| Black News / modern | Add via `gt submit` after `--low-latency` runs |

## Local workflow

```bash
# 1. Fetch GT (or grow corpus over time)
historical-ocr gt fetch --limit 500 --val-ratio 0.1

# 2. Optional: add corrected modern pages
historical-ocr run myjob -i scan.tif --mode print --low-latency
historical-ocr gt template myjob
# edit jobs/myjob/export/*.corrected.txt
historical-ocr gt submit --job myjob

# 3. Merge → Kraken manifest
historical-ocr newspaper prepare

# 4. Train (needs kraken: pip install kraken)
historical-ocr newspaper train --epochs 30

# 5. Eval val split (rules-only baseline vs GT)
historical-ocr newspaper eval --split val --limit 50
```

Prepared layout: `data/newspaper_ocr/{train,val}/{images,text}/` + `ketos/train.txt`.

## Bridges (GPU)

```bash
NEWSPAPER_GT_LIMIT=2000 bash scripts/submit_bridges_newspaper_ocr.sh
```

Jobs: `newspaper-gt-fetch` (download + prepare) → `newspaper-ocr-train` (Kraken).

Monitor:

```bash
ssh bridges2 squeue -u $USER
ssh bridges2 tail -f /ocean/projects/hum260002p/$USER/historical-ocr/newspaper-ocr-train-*.out
```

## Notes

- **1770–1810** CA pages train the Kraken model; **1970 Black News** needs `gt submit` corrections (no public GT).
- **Tune rules** (`gt tune`) remain the fast LLM-free path for Tesseract; Kraken is the learned OCR model.
- Minimum **10 train lines** before `newspaper train` will run.
