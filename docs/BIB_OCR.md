# bib-ocr integration

[bib-ocr](https://github.com/buzzcauldron/bib-ocr) extracts bibliography citations from academic PDFs (DOI scan → hyperlink crawl → reference-section OCR → footnotes → inline citations). historical-ocr **vendors the preprocessing and density heuristics** and optionally calls the full package.

## Built in (no extra install)

| Component | Role |
|-----------|------|
| `prepare_for_tesseract` | Invert + contrast pipeline for scanned print pages |
| `bib_density` | Find sparse / citation-heavy PDF pages for OCR fallback |
| `bib_section_heads` | Detect References / Bibliography headings |
| `pdf_text_first` mode | Uses bib preprocessing on Tesseract fallback @ 300 DPI |
| Job artifact | `artifacts/<pdf>_density.png` heatmap when matplotlib is installed |

Env:

```
HISTORICAL_OCR_BIB_PREPROCESS=1
HISTORICAL_OCR_PDF_DENSITY_OCR=1
```

Per doc-type YAML you can set `preprocess.bib_preprocess: true` or `binarise: true`.

## Optional full bib-ocr package

```bash
pip install -e ../bib-ocr
historical-ocr tools                    # should show ✓ bib-ocr
historical-ocr bib-ocr paper.pdf -v
historical-ocr bib-ocr paper.pdf --json
historical-ocr bib-ocr paper.pdf --max-stage 3   # through ref_section OCR only
```

Same five-stage cascade as Research Party compile Step 2.0 — see bib-ocr README.

## When to use which

| Task | Tool |
|------|------|
| Full book / EEBO page images | `historical-ocr run` + Tesseract doc types |
| Modern PDF with embedded text | `--ocr-combination pdf_text_first` (uses bib preprocess on fallback) |
| Citation list / bibliography only from PDF | `historical-ocr bib-ocr` or install bib-ocr in Research Party |
