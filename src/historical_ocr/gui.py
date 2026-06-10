"""Desktop GUI for historical-ocr (tkinter, modeled on transcriber-shell).

Run: historical-ocr gui
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None  # type: ignore[misc, assignment]
    DND_FILES = None  # type: ignore[misc, assignment]

from historical_ocr.config import Settings
from historical_ocr.document_types import list_print_doc_types, list_print_languages
from historical_ocr.gui_state import load_gui_state, save_gui_state
from historical_ocr.pipeline.run_job import run_job

_BG = "#f6f4ef"
_FG = "#1f1f1f"
_MUTED = "#4a4a4a"
_ACCENT = "#2f3f4f"
_FIELD_BG = "#fffcf7"

_INPUT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_prompt() -> str:
    candidate = _repo_root().parent / "transcription-shell" / "fixtures" / "prompt.example.yaml"
    return str(candidate) if candidate.is_file() else ""


class HistoricalOcrGui:
    def __init__(self) -> None:
        self._dnd_available = False
        if TkinterDnD is not None:
            try:
                self.root = TkinterDnD.Tk()
                self._dnd_available = True
            except (RuntimeError, tk.TclError, OSError):
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("Historical OCR")
        self.root.minsize(640, 720)
        self.root.configure(bg=_BG)

        self._settings = Settings()
        self._log_q: queue.Queue[str] = queue.Queue(maxsize=4000)
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._sources: list[Path] = []
        self._job_id = tk.StringVar(value="job1")
        self._url = tk.StringVar(value="")
        self._mode = tk.StringVar(value="auto")
        self._print_doc_type = tk.StringVar(value=self._settings.print_doc_type or "auto")
        self._publication_year = tk.StringVar(
            value=str(self._settings.publication_year or ""),
        )
        self._print_language = tk.StringVar(value=self._settings.print_language or "auto")
        self._ocr_combination = tk.StringVar(value=self._settings.ocr_combination)
        self._prompt = tk.StringVar(value=_default_prompt())
        self._fingerprint = tk.BooleanVar(value=False)
        self._clean = tk.BooleanVar(value=self._settings.clean_print)
        self._max_width = tk.IntVar(value=self._settings.max_image_width)
        self._jpeg_quality = tk.IntVar(value=self._settings.jpeg_quality)
        self._status = tk.StringVar(value="Ready.")
        self._last_job_root: Path | None = None

        self._build_ui()
        self._load_state()
        self._poll_log()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Historical OCR", font=("Georgia", 18))
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            outer,
            text="Acquire → normalize → route → OCR/transcribe → TEI + PAGE-XML + clean TXT",
            foreground=_MUTED,
        )
        subtitle.pack(anchor=tk.W, pady=(0, 10))

        files_frame = ttk.LabelFrame(outer, text="Sources (PDF or images)", padding=8)
        files_frame.pack(fill=tk.BOTH, expand=True)

        self._files_list = tk.Listbox(
            files_frame,
            height=8,
            bg=_FIELD_BG,
            fg=_FG,
            selectbackground=_ACCENT,
        )
        self._files_list.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scroll = ttk.Scrollbar(files_frame, command=self._files_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._files_list.configure(yscrollcommand=scroll.set)

        if self._dnd_available and DND_FILES is not None:
            self._files_list.drop_target_register(DND_FILES)
            self._files_list.dnd_bind("<<Drop>>", self._on_drop)

        btn_row = ttk.Frame(files_frame)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="Add files…", command=self._add_files).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Add folder…", command=self._add_folder).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Remove", command=self._remove_selected).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Clear", command=self._clear_files).pack(side=tk.LEFT, padx=6)

        opts = ttk.LabelFrame(outer, text="Job options", padding=8)
        opts.pack(fill=tk.X, pady=10)

        row1 = ttk.Frame(opts)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="Job ID").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Entry(row1, textvariable=self._job_id, width=24).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(row1, text="Mode").grid(row=0, column=2, sticky=tk.W, padx=(16, 8))
        ttk.Combobox(
            row1,
            textvariable=self._mode,
            values=["auto", "print", "manuscript"],
            width=14,
            state="readonly",
        ).grid(row=0, column=3, sticky=tk.W)

        row1b = ttk.Frame(opts)
        row1b.pack(fill=tk.X, pady=4)
        ttk.Label(row1b, text="Language").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Combobox(
            row1b,
            textvariable=self._print_language,
            values=[x.code for x in list_print_languages()],
            width=8,
            state="readonly",
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(row1b, text="Year").grid(row=0, column=2, sticky=tk.W, padx=(12, 8))
        ttk.Entry(row1b, textvariable=self._publication_year, width=6).grid(row=0, column=3, sticky=tk.W)
        ttk.Label(row1b, text="Print type").grid(row=0, column=4, sticky=tk.W, padx=(12, 8))
        print_types = ["auto"] + list_print_doc_types()
        ttk.Combobox(
            row1b,
            textvariable=self._print_doc_type,
            values=print_types,
            width=18,
        ).grid(row=0, column=5, sticky=tk.W)

        row1c = ttk.Frame(opts)
        row1c.pack(fill=tk.X, pady=4)
        ttk.Label(row1c, text="OCR fork").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Combobox(
            row1c,
            textvariable=self._ocr_combination,
            values=[
                "tesseract_then_clean",
                "tesseract_only",
                "pdf_text_first",
                "shell_print",
            ],
            width=22,
            state="readonly",
        ).grid(row=0, column=1, sticky=tk.W)

        row2 = ttk.Frame(opts)
        row2.pack(fill=tk.X, pady=6)
        ttk.Label(row2, text="URL (optional)").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Entry(row2, textvariable=self._url, width=72).grid(row=0, column=1, columnspan=3, sticky=tk.EW)
        row2.columnconfigure(1, weight=1)

        row3 = ttk.Frame(opts)
        row3.pack(fill=tk.X, pady=6)
        ttk.Label(row3, text="Prompt YAML").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Entry(row3, textvariable=self._prompt, width=52).grid(row=0, column=1, sticky=tk.EW)
        ttk.Button(row3, text="Browse…", command=self._browse_prompt).grid(row=0, column=2, padx=6)
        row3.columnconfigure(1, weight=1)

        row4 = ttk.Frame(opts)
        row4.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(row4, text="Type-case fingerprint", variable=self._fingerprint).pack(side=tk.LEFT)
        ttk.Checkbutton(row4, text="Underwood clean (print)", variable=self._clean).pack(side=tk.LEFT, padx=12)
        ttk.Label(row4, text="Max width").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Spinbox(row4, from_=800, to=8000, increment=100, textvariable=self._max_width, width=6).pack(
            side=tk.LEFT,
        )
        ttk.Label(row4, text="JPEG Q").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Spinbox(row4, from_=60, to=100, increment=1, textvariable=self._jpeg_quality, width=4).pack(
            side=tk.LEFT,
        )

        log_frame = ttk.LabelFrame(outer, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self._log = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            bg=_FIELD_BG,
            fg=_FG,
            state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))
        self._run_btn = ttk.Button(bottom, text="Run pipeline", command=self._start_run)
        self._run_btn.pack(side=tk.LEFT)
        ttk.Button(bottom, text="Open job folder", command=self._open_job).pack(side=tk.LEFT, padx=8)
        ttk.Button(bottom, text="Tools check", command=self._tools_check).pack(side=tk.LEFT)
        ttk.Label(bottom, textvariable=self._status, foreground=_MUTED).pack(side=tk.RIGHT)

    def _append_log(self, line: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, line + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _poll_log(self) -> None:
        try:
            while True:
                self._append_log(self._log_q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log)

    def _on_drop(self, event) -> None:
        for raw in self.root.tk.splitlist(event.data):
            path = Path(raw.strip("{}"))
            if path.is_file():
                self._add_path(path)

    def _add_path(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if path.suffix.lower() not in _INPUT_SUFFIXES:
            return
        if path not in self._sources:
            self._sources.append(path)
            self._files_list.insert(tk.END, str(path))

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDFs or images",
            filetypes=[
                ("Historical sources", "*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        for p in paths:
            self._add_path(Path(p))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder")
        if not folder:
            return
        root = Path(folder)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in _INPUT_SUFFIXES:
                self._add_path(path)

    def _remove_selected(self) -> None:
        sel = list(self._files_list.curselection())
        for idx in reversed(sel):
            self._files_list.delete(idx)
            del self._sources[idx]

    def _clear_files(self) -> None:
        self._sources.clear()
        self._files_list.delete(0, tk.END)

    def _browse_prompt(self) -> None:
        path = filedialog.askopenfilename(
            title="Transcription prompt YAML",
            filetypes=[("YAML", "*.yaml *.yml"), ("All", "*.*")],
        )
        if path:
            self._prompt.set(path)

    def _tools_check(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "historical_ocr.cli", "tools"],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
        )
        self._append_log(proc.stdout.strip() or proc.stderr.strip())

    def _open_job(self) -> None:
        if self._last_job_root and self._last_job_root.is_dir():
            if sys.platform == "darwin":
                subprocess.run(["open", str(self._last_job_root)], check=False)
            else:
                webbrowser.open(self._last_job_root.as_uri())
        else:
            messagebox.showinfo("Historical OCR", "No completed job folder yet.")

    def _start_run(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Historical OCR", "A job is already running.")
            return

        job_id = self._job_id.get().strip()
        if not job_id:
            messagebox.showerror("Historical OCR", "Job ID is required.")
            return
        if not self._url.get().strip() and not self._sources:
            messagebox.showerror("Historical OCR", "Add source files or a URL.")
            return
        if self._mode.get() == "manuscript" and not self._prompt.get().strip():
            messagebox.showerror("Historical OCR", "Manuscript mode requires a prompt YAML.")
            return

        self._stop_event.clear()
        self._run_btn.configure(state=tk.DISABLED)
        self._status.set("Running…")
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    def _run_worker(self) -> None:
        try:
            settings = self._settings.model_copy(
                update={
                    "max_image_width": int(self._max_width.get()),
                    "jpeg_quality": int(self._jpeg_quality.get()),
                    "clean_print": bool(self._clean.get()),
                    "print_doc_type": self._print_doc_type.get().strip() or "auto",
                    "print_language": self._print_language.get().strip() or "auto",
                    "publication_year": (
                        int(self._publication_year.get())
                        if self._publication_year.get().strip().isdigit()
                        else None
                    ),
                    "ocr_combination": self._ocr_combination.get().strip(),
                },
            )
            url = self._url.get().strip() or None
            prompt = Path(self._prompt.get()).expanduser() if self._prompt.get().strip() else None
            manifest = run_job(
                self._job_id.get().strip(),
                url=url,
                inputs=self._sources or None,
                settings=settings,
                mode=self._mode.get(),
                prompt=prompt,
                fingerprint=bool(self._fingerprint.get()),
                clean=bool(self._clean.get()),
                print_doc_type=settings.print_doc_type,
                ocr_combination=settings.ocr_combination,
                publication_year=settings.publication_year,
                print_language=settings.print_language,
                log_fn=lambda m: self._log_q.put(m),
            )
            self._last_job_root = (settings.jobs_dir / manifest.job_id).expanduser().resolve()
            self._log_q.put(json.dumps(manifest.export, indent=2))
            self.root.after(0, lambda: self._status.set(f"Done — {self._last_job_root}"))
        except Exception as exc:
            self._log_q.put(f"error: {exc}")
            self.root.after(0, lambda: self._status.set("Failed."))
        finally:
            self.root.after(0, lambda: self._run_btn.configure(state=tk.NORMAL))

    def _state_dict(self) -> dict:
        return {
            "job_id": self._job_id.get(),
            "url": self._url.get(),
            "mode": self._mode.get(),
            "print_language": self._print_language.get(),
            "print_doc_type": self._print_doc_type.get(),
            "publication_year": self._publication_year.get(),
            "ocr_combination": self._ocr_combination.get(),
            "prompt": self._prompt.get(),
            "fingerprint": self._fingerprint.get(),
            "clean": self._clean.get(),
            "max_width": int(self._max_width.get()),
            "jpeg_quality": int(self._jpeg_quality.get()),
            "sources": [str(p) for p in self._sources],
        }

    def _load_state(self) -> None:
        data = load_gui_state()
        if not data:
            return
        self._job_id.set(str(data.get("job_id", self._job_id.get())))
        self._url.set(str(data.get("url", "")))
        self._mode.set(str(data.get("mode", "auto")))
        self._print_language.set(str(data.get("print_language", self._print_language.get())))
        self._print_doc_type.set(str(data.get("print_doc_type", self._print_doc_type.get())))
        self._publication_year.set(str(data.get("publication_year", self._publication_year.get())))
        self._ocr_combination.set(str(data.get("ocr_combination", self._ocr_combination.get())))
        self._prompt.set(str(data.get("prompt", self._prompt.get())))
        self._fingerprint.set(bool(data.get("fingerprint", False)))
        self._clean.set(bool(data.get("clean", True)))
        if "max_width" in data:
            self._max_width.set(int(data["max_width"]))
        if "jpeg_quality" in data:
            self._jpeg_quality.set(int(data["jpeg_quality"]))
        for raw in data.get("sources", []):
            path = Path(str(raw))
            if path.is_file():
                self._add_path(path)

    def _on_close(self) -> None:
        try:
            save_gui_state(self._state_dict())
        except OSError:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    HistoricalOcrGui().run()


if __name__ == "__main__":
    main()
