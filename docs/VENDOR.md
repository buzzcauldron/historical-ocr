# Vendored code

Only minimal, stable utilities are copied into `src/historical_ocr/lib/`. Heavy ML/browser pipelines stay in their home repos and are invoked via subprocess.

| Module | Source | Notes |
|--------|--------|-------|
| `image_tools/convert.py` | transcription-shell `image_tools/convert.py` | TIF→JPEG, PAGE-XML scale, optional cuCIM resize; + `max_pixels` for ingest |
| `lib/document_export.py` | historical-ocr | Production `document.txt` + merged TEI + `delivery.json` |
| `lib/fetch.py` | transcription-shell `strigil_fetch.py`, strigil IIIF patterns | Slim HTTP + IIIF manifest + HTML img fallback |
| `lib/pdf_pages.py` | transcription-shell `pipeline/pdf_extract.py` | pymupdf rasterization |
| `lib/print_ocr.py` | research-party `cli/bib_pdf_ocr.py` | pypdf → Tesseract fallback per page |
| `lib/bib_density.py` | [bib-ocr](https://github.com/buzzcauldron/bib-ocr) `density.py` | Citation-density PDF page targeting |
| `lib/bib_section_heads.py` | bib-ocr `section_heads.py` | Bibliography heading patterns |
| `ocr/preprocess.py` | bib-ocr `preprocessing.py` / witchofthewires/biblio | `prepare_for_tesseract` invert+contrast |
| `lib/protocol_text.py` | transcription-shell `pipeline/run.py` | Plain text from protocol YAML |
| `lib/tei_minimal.py` | transcription-shell `xml_tools/tei.py` | Body `<p>` / `<lb>` + `<figure>` for `[fig:id]` |
| `figures/` + `pipeline/figure_extract.py` | transcription-shell `figures/` | DocLayNet detection, crops, `[fig:id]` markers |

## Backends (subprocess / sibling import)

| Backend | Source | Notes |
|---------|--------|-------|
| `backends/ocr_cleanup.py` | [tedunderwood/DataMunging](https://github.com/tedunderwood/DataMunging) via sibling `ocr-cleanup` | Rule-based print normalization; rulesets not duplicated here |
| `backends/transcriber_shell.py` | transcription-shell CLI | Manuscript transcription |
| `backends/fingerprint.py` | manuscript-fingerprint CLI | Type-case scan |
| `backends/bib_ocr.py` | [bib-ocr](https://github.com/buzzcauldron/bib-ocr) | Optional PDF bibliography citation cascade |

## Not vendored

- **strigil** — full repository adapters (EEBO, HathiTrust bypass, crawl). Use strigil directly for complex acquire; historical-ocr fetch covers common IIIF/HTML cases.
- **transcription-shell** — lineation, HTR, LLM, schema validation.
- **manuscript-fingerprint** — Kraken segmentation, type-case models, P&P matching.
- **research-party** — bibliography OCR, citation graphs, pack compiler.
- **DataMunging rulesets** (~15 MB) — live in `ocr-cleanup/rulesets/`; see [ECOSYSTEM.md](ECOSYSTEM.md).
