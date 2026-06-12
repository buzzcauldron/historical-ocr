# Historical OCR — guide for non-experts

This tool turns **scanned books, PDFs, and page images** into **plain text** you can search, quote, and reuse. It is aimed at historians, librarians, and researchers who have source material and want a simple tool to make passable ocr scans of tricky historical documents. Send a DM for suggestions and bugs.

---

## Simple GUI

```bash
historical-ocr gui
```

1. Paste an **API key** (optional) — provider is detected automatically.
2. Choose **Free** (~5 s/page, rules + your tune rules), **Medium** (~6 s, glyph filter), or **High** (~30–60 s, + AI clean when a key is set).
3. **Training loop:** Run → edit `export/*.corrected.txt` → **Teach** to update tune rules (no LLM needed).

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

You only need to do this once per computer. The steps below assume a **Mac** with macOS 12 or later. Linux instructions follow.

---

### macOS — step by step

**Step 1 — Install Homebrew** (the macOS package manager)

Open **Terminal** (search "Terminal" in Spotlight) and paste:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
```

Follow the prompts. When it asks for your password, type it (nothing will appear — that is normal). If Homebrew is already installed, this is harmless. When it finishes, close and reopen Terminal.

**Step 2 — Install Python 3.11 or later**

```bash
brew install python@3.11
```

Check it worked:

```bash
python3 --version
# should print Python 3.11.x or higher
```

**Step 3 — Install system Tk** (needed for the drag-and-drop GUI)

Homebrew's Python does not include tkinter by default. Install the matching version:

```bash
brew install python-tk@3.11
```

If you installed a different Python version (e.g. 3.12), replace `3.11` with your version number.

**Step 4 — Install Tesseract and Poppler** (the OCR engine and PDF renderer)

```bash
brew install tesseract tesseract-lang poppler
```

This installs Tesseract with language packs for English, Latin, German, French, Italian, Spanish, and Fraktur (old German type).

**Step 5 — Download and set up the tool**

If you have not already cloned the repository:

```bash
cd ~/Projects   # or wherever you keep code
git clone https://github.com/buzzcauldron/historical-ocr.git "historical ocr"
cd "historical ocr"
```

If you already have the folder, just navigate to it:

```bash
cd "/path/to/historical ocr"
```

Now run the installer:

```bash
bash scripts/install.sh
```

This creates a Python virtual environment (`.venv`), installs all Python dependencies, and installs Playwright's Chromium browser.

**Step 6 — Activate the environment**

```bash
source .venv/bin/activate
```

You need to run this command each time you open a new Terminal window before using the tool. Add it to your shell profile (`~/.zshrc`) to make it automatic:

```bash
echo 'source "/path/to/historical ocr/.venv/bin/activate"' >> ~/.zshrc
```

**Step 7 — Add API keys** (optional — needed for AI cleanup)

```bash
cp .env.example .env
open .env   # opens in TextEdit
```

Add your key(s). You only need one:

```
ANTHROPIC_API_KEY=sk-ant-...   # for Medium / High tier (Claude Haiku / Sonnet)
GOOGLE_API_KEY=AIza...         # alternative for High tier (Gemini 2.5 Pro)
```

Free tier (Tesseract + rule-based cleanup) works without any API key.

**Step 8 — Launch**

```bash
historical-ocr-gui
```

The GUI window will open. If you see an error about tkinter, make sure step 3 used the correct Python version number.

---

### Verify the install

```bash
historical-ocr --version
historical-ocr tools
```

You want a **✓** next to **tesseract**. A ✓ next to **playwright** is needed only for URL fetching.

---

### Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install -y \
  python3.11 python3.11-venv python3-tk \
  tesseract-ocr poppler-utils \
  tesseract-ocr-eng tesseract-ocr-lat tesseract-ocr-deu \
  tesseract-ocr-fra tesseract-ocr-ita tesseract-ocr-spa \
  tesseract-ocr-script-fraktur

cd "/path/to/historical ocr"
bash scripts/install.sh
source .venv/bin/activate
```

---

### Troubleshooting

**"No module named tkinter"** — Run `brew install python-tk@<your-python-version>` (macOS) or `sudo apt install python3-tk` (Linux).

**"tesseract: command not found"** — Run `brew install tesseract tesseract-lang poppler` (macOS) or the `apt install` line above (Linux).

**"pdftoppm: command not found" / PDF pages blank** — Poppler is not installed. Run `brew install poppler` (macOS) or `sudo apt install poppler-utils` (Linux).

**GUI window is blank or does not open** — Make sure you activated the venv (`source .venv/bin/activate`) before running `historical-ocr-gui`.

**"Nothing fetched from URL"** — Playwright's Chromium may not be installed. Run `python -m playwright install chromium`.

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
No OCR is perfect, especially on damaged scans or unusual type. For printed English after about 1700, the tool can **normalize** spelling (optional, on by default) so the text is easier to compare with modern sources.

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

### Faster runs

For speed over optional extras, add **`--fast`**:

```bash
historical-ocr run my-job -i scan.tif --mode print --fast
```

`--fast` uses smaller page images, text-only Tesseract (skips per-word layout), skips Underwood cleanup, and skips internal per-page XML copies. You still get the main **`.txt`** and **`.xml`** deliverables.
