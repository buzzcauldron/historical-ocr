# Page CNN training (print vs manuscript)

ResNet18 classifier used when `--mode auto`. Training data lives under `data/page_cnn/{print,manuscript}/`.

## Quick start (local)

```bash
pip install -e ".[ml]"
python scripts/bootstrap_page_cnn_data.py          # small local seeds
historical-ocr cnn sources                         # registry
historical-ocr cnn fetch --source ocr-quality --source ocr-pdf-degraded
historical-ocr cnn train --out models/page_cnn.pt
export HISTORICAL_OCR_PAGE_CNN_MODEL=models/page_cnn.pt
historical-ocr run job -i book.pdf --mode auto
```

## Registered sources

| Source | Class | Origin |
|--------|-------|--------|
| `ocr-quality` | print | [OCR-Quality](https://huggingface.co/datasets/Aslan-mingye/OCR-Quality) — [arxiv:2510.21774](https://arxiv.org/html/2510.21774v1) |
| `ocr-pdf-degraded` | print | [racineai/ocr-pdf-degraded](https://huggingface.co/datasets/racineai/ocr-pdf-degraded) |
| `pixparse-pdfa` | print | [pixparse/pdfa-eng-wds](https://huggingface.co/datasets/pixparse/pdfa-eng-wds) (streamed sample) |
| `pixparse-idl` | print | [pixparse/idl-wds](https://huggingface.co/datasets/pixparse/idl-wds) (streamed sample) |
| `iam-histdb`, `pinkas`, … | manuscript | [xinke-wang/OCRDatasets](https://github.com/xinke-wang/OCRDatasets) catalog (local checkout) |
| `akdeniz-kraken-*` | manuscript | Akdeniz kraken GT synced to Bridges |

Pixparse PDF corpora: [PDF Document / OCR Datasets](https://huggingface.co/collections/pixparse/pdf-document-ocr-datasets).

### Fetch examples

```bash
# Default HF print sets (ocr-quality + ocr-pdf-degraded)
historical-ocr cnn fetch

# All Hugging Face sources (includes pixparse; use --limit for huge sets)
historical-ocr cnn fetch --all-hf --limit 500

# OCRDatasets historical manuscripts (download dataset into checkout first)
git clone https://github.com/xinke-wang/OCRDatasets ~/OCRDatasets
historical-ocr cnn fetch --ocrdatasets iam-histdb --ocrdatasets-root ~/OCRDatasets/data

# Arbitrary local folders
historical-ocr cnn fetch --extra print:/path/to/scans --extra manuscript:/path/to/mss
```

Fetched images and provenance are tracked in `data/page_cnn/manifest.json`.

## Adding more training data

Any time, without re-fetching:

```bash
# Copy into the canonical tree
historical-ocr cnn fetch --extra manuscript:/new/manuscript/pages

# Or keep a separate tree and merge at train time
historical-ocr cnn train --data data/page_cnn --extra-data /other/page_cnn_root
```

Extra roots must contain `print/` and/or `manuscript/` subfolders (nested images OK).

## Bridges2 + Akdeniz

On **Akdeniz**, sync manuscript GT to Bridges:

```bash
bash scripts/xfer_akdeniz_page_cnn_to_bridges.sh
```

On **Bridges** login:

```bash
export HISTORICAL_OCR_ROOT=/ocean/projects/hum260002p/sstrickland/historical-ocr
bash scripts/bridges_fetch_page_cnn.sh    # HF print corpora
sbatch scripts/bridges_train_page_cnn.sbatch
```

Environment overrides:

| Variable | Default |
|----------|---------|
| `PAGE_CNN_DATA` | `$ROOT/data/page_cnn` |
| `PAGE_CNN_MODEL` | `$ROOT/models/page_cnn.pt` |
| `PAGE_CNN_EPOCHS` | `25` |
| `PAGE_CNN_PIXPARSE_LIMIT` | unset (skip pixparse unless set) |
| `PAGE_CNN_AKDENIZ_GT` | `$ROOT/data/akdeniz-gt` |

Pull trained model locally:

```bash
scp bridges2-dtn:/ocean/projects/hum260002p/sstrickland/historical-ocr/models/page_cnn.pt models/
```
