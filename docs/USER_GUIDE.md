# Historical OCR — guide for non-experts

This tool turns **scanned books, PDFs, and page images** into **plain text** you can search, quote, and reuse. It is aimed at historians, librarians, and researchers who have source material but do not want to become OCR engineers.

---

## What you get

After a run finishes, open the job folder and look in **`export/`**. These are the files meant for everyday use:

| File | What it is |
|------|------------|
| **`{your-file-name}.txt`** | The full text of your source, in reading order (e.g. `BlackNews_19700110_002.txt`). Open it in Word, Notes, or any text editor. |
| **`{your-file-name}.xml`** | The same content in **TEI XML** — a standard format archives and digital-humanities tools often expect. |
| **`{your-file-name}.delivery.json`** | A short note about *how* the file was produced (date, language settings, source URL, etc.). |
| **`checksums.sha256`** | A fingerprint so you can prove the files have not been changed. |

Everything else in the job folder (folders named `ocr`, `clean`, `_internal`, and so on) is **working material**. You can ignore it unless something went wrong and you need help debugging.

---

## What kind of material do you have?

| Your material | What to choose |
|---------------|----------------|
| A **printed book or pamphlet** (even very old type) | **Print** mode |
| **Handwriting** (letters, charters, notebooks) | **Manuscript** mode (needs extra setup — see below) |
| **Not sure** | **Auto** mode (the tool guesses print vs handwriting per page) |

**Tip:** If you know roughly **when** something was printed (e.g. 1688, 1850), enter the year. The tool picks better OCR settings for that era.

**Tip:** Pick a **language** if it is not English (Latin, German, French, etc.).

---

## Easiest path: desktop app

If you prefer clicking to typing commands:

1. **Install once** (see [One-time setup](#one-time-setup) below).
2. Start the app:
   ```bash
   historical-ocr gui
   ```
3. Drag your **PDF or images** into the file list (or use **Add files**).
4. Give the job a short name (e.g. `sermon_1688`).
5. Choose **Print**, **Manuscript**, or **Auto**.
6. Click **Run** and wait for the log to say it is done.
7. Open **`jobs/<your job name>/export/<your-file-name>.txt`** (same stem as the file you submitted).

---

## Command-line path (copy and paste)

Good if you are comfortable in Terminal.

**Process a PDF on your computer:**

```bash
historical-ocr run my-book -i ~/Downloads/scan.pdf --mode print --publication-year 1850
```

**Process a file from the web** (when you have a direct link to a PDF or IIIF manifest):

```bash
historical-ocr run my-book --url "https://example.org/manifest.json" --mode auto
```

**Open your results:**

```bash
open jobs/my-book/export/my-book.txt    # macOS — use your source file's name
```

To rebuild exports without re-OCRing everything:

```bash
historical-ocr export my-book
```

---

## One-time setup

You only need to do this once per computer.

### macOS (simplest)

```bash
cd "/path/to/historical ocr"
bash scripts/install.sh
source .venv/bin/activate
```

The install script also tries to install **Tesseract** (the program that reads printed text). If that step fails, run:

```bash
brew install tesseract tesseract-lang poppler
```

### Check that the basics work

```bash
historical-ocr --version
historical-ocr tools
```

You want a **✓** next to **tesseract** for printed books.

---

## Manuscripts (handwriting) — extra steps

Handwritten sources need **transcription-shell** and an **API key** (for cloud transcription). That is more involved than print OCR.

1. Install [transcription-shell](https://github.com/buzzcauldron/transcription-shell) separately.
2. Copy `.env.example` to `.env` and add your API key.
3. Point the run at a **prompt** file (a recipe that tells the model how to transcribe).

Example:

```bash
historical-ocr run charter-job \
  -i page.jpg \
  --mode manuscript \
  --prompt ../transcription-shell/fixtures/prompt.example.yaml
```

If you only work with **printed** material, you can skip all of this.

---

## Common questions

**How long does it take?**  
A few seconds per page for print OCR on a modern laptop. Large PDFs and manuscript runs can take much longer.

**Will the text be perfect?**  
No OCR is perfect, especially on damaged scans or unusual type. For old printed English after about 1700, the tool can **normalize** spelling (optional, on by default) so the text is easier to compare with modern sources.

**My PDF already has selectable text — why OCR?**  
The tool tries embedded text first when that option is on. OCR is a fallback for scanned pages where the text layer is missing or poor.

**What is TEI / XML?**  
The `.xml` file is for systems that understand structured academic markup. If you only need to read or search the work, the **`.txt`** file is enough.

**Where did my job go?**  
Under **`jobs/<job name>/`**, relative to the project folder. Each job is self-contained.

**Something failed — what now?**  
Run `historical-ocr status <job name>` and read the log in the GUI, or check `manifest.json` in the job folder. Run `historical-ocr tools` to see if Tesseract or other helpers are missing.

---

## Words you might see

| Term | Plain meaning |
|------|----------------|
| **OCR** | Optical character recognition — software that reads letters in an image |
| **Print** | Machine-set type (books, newspapers, pamphlets) |
| **Manuscript** | Handwritten |
| **IIIF** | A standard way libraries share page images on the web |
| **TEI** | Text Encoding Initiative — a common XML format for scholarly texts |
| **Job** | One batch of work (one book or one upload) with its own output folder |
| **Normalization** | Light cleanup of old spelling so text is easier to use (can be turned off) |

---

## More detail (for when you need it)

- Technical README: [README.md](../README.md)
- Print settings by century: [PRINT_OCR.md](PRINT_OCR.md)
- Bibliography PDF tools: [BIB_OCR.md](BIB_OCR.md)

---

## Quick reference

```bash
historical-ocr gui                              # desktop app
historical-ocr run JOB -i file.pdf --mode print # printed book
historical-ocr run JOB --url URL --mode auto    # from the web
historical-ocr export JOB                       # rebuild export files
historical-ocr tools                            # is everything installed?
```

Your finished text: **`jobs/JOB/export/<source-filename>.txt`** (matches the name of the file you submitted)
