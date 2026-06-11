"""Simple desktop GUI — API key, quality tier, training loop."""

from __future__ import annotations

import json
import queue
import shutil
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
from historical_ocr.lib.api_detect import detect_provider, provider_label
from historical_ocr.lib.quality_presets import QualityTier, apply_quality_tier, tier_label, tier_run_flags
from historical_ocr.lib.training_loop import correction_template_path, teach_from_job, tune_rule_count
from historical_ocr.gui_state import load_gui_state, save_gui_state
from historical_ocr.pipeline.run_job import run_job


def _companion_status() -> list[tuple[str, bool, str]]:
    """Return (label, installed, install_hint) for each companion tool."""
    return [
        (
            "transcriber-shell",
            shutil.which("transcriber-shell") is not None,
            "pip install transcriber-shell",
        ),
        (
            "strigil",
            shutil.which("strigil") is not None,
            "pip install strigil",
        ),
    ]

_BG = "#f6f4ef"
_FG = "#1f1f1f"
_MUTED = "#4a4a4a"
_ACCENT = "#2f3f4f"
_FIELD_BG = "#fffcf7"

_INPUT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
_STATE_VERSION = 4


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
        self.root.minsize(520, 560)
        self.root.geometry("600x680")
        self.root.configure(bg=_BG)

        self._settings = Settings()
        self._log_q: queue.Queue[str] = queue.Queue(maxsize=4000)
        self._worker: threading.Thread | None = None

        self._sources: list[Path] = []
        self._url_sources: list[str] = []
        self._job_id = tk.StringVar(value="job1")
        self._api_key = tk.StringVar(value="")
        self._provider_label = tk.StringVar(value=provider_label("none"))
        self._quality = tk.StringVar(value="medium")
        self._review_png = tk.BooleanVar(value=True)
        self._review_conf_threshold = tk.StringVar(value="65")
        self._publication_year = tk.StringVar(value="1970")
        self._rules_count = tk.StringVar(value="0 rules learned")
        self._status = tk.StringVar(value="Ready.")
        self._last_job_id: str | None = None
        self._last_job_root: Path | None = None

        self._build_ui()
        self._load_state()
        self._on_api_key_change()
        self._refresh_rules_count()
        self._poll_log()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Top bar: title + always-visible Run button ────────────────────
        top = ttk.Frame(outer)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text="Historical OCR", font=("Georgia", 16)).pack(side=tk.LEFT)
        self._run_btn = ttk.Button(top, text="▶  Run", command=self._start_run, width=12)
        self._run_btn.pack(side=tk.RIGHT)
        ttk.Button(top, text="Open output", command=self._open_job).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        # ── Sources ───────────────────────────────────────────────────────
        files_frame = ttk.LabelFrame(outer, text="Sources — files, folders, or URLs", padding=6)
        files_frame.pack(fill=tk.BOTH, expand=True)

        list_row = ttk.Frame(files_frame)
        list_row.pack(fill=tk.BOTH, expand=True)
        self._files_list = tk.Listbox(list_row, height=5, bg=_FIELD_BG, fg=_FG, selectbackground=_ACCENT)
        self._files_list.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scroll = ttk.Scrollbar(list_row, command=self._files_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._files_list.configure(yscrollcommand=scroll.set)
        if self._dnd_available and DND_FILES is not None:
            self._files_list.drop_target_register(DND_FILES)
            self._files_list.dnd_bind("<<Drop>>", self._on_drop)

        brow = ttk.Frame(files_frame)
        brow.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(brow, text="Add files…", command=self._add_files).pack(side=tk.LEFT)
        ttk.Button(brow, text="Add folder…", command=self._add_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(brow, text="Clear", command=self._clear_files).pack(side=tk.LEFT, padx=4)

        url_row = ttk.Frame(files_frame)
        url_row.pack(fill=tk.X, pady=(4, 0))
        self._url_var = tk.StringVar()
        ttk.Label(url_row, text="URL").pack(side=tk.LEFT)
        url_entry = ttk.Entry(url_row, textvariable=self._url_var)
        url_entry.pack(side=tk.LEFT, padx=(6, 4), fill=tk.X, expand=True)
        url_entry.bind("<Return>", lambda _e: self._add_url())
        ttk.Button(url_row, text="Add", command=self._add_url).pack(side=tk.LEFT)

        # ── Settings row: quality + meta ─────────────────────────────────
        settings_row = ttk.Frame(outer)
        settings_row.pack(fill=tk.X, pady=6)

        qual_frame = ttk.LabelFrame(settings_row, text="Quality", padding=4)
        qual_frame.pack(side=tk.LEFT, fill=tk.Y)
        for tier in ("free", "medium", "high"):
            ttk.Radiobutton(
                qual_frame,
                text=tier_label(tier),  # type: ignore[arg-type]
                variable=self._quality,
                value=tier,
            ).pack(anchor=tk.W)

        meta_frame = ttk.Frame(settings_row)
        meta_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        key_frame = ttk.LabelFrame(meta_frame, text="API key", padding=4)
        key_frame.pack(fill=tk.X)
        self._api_entry = ttk.Entry(key_frame, textvariable=self._api_key, show="•")
        self._api_entry.pack(fill=tk.X)
        self._api_key.trace_add("write", lambda *_: self._on_api_key_change())
        ttk.Label(key_frame, textvariable=self._provider_label, foreground=_MUTED).pack(anchor=tk.W, pady=(2, 0))

        job_row = ttk.Frame(meta_frame)
        job_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(job_row, text="Year").pack(side=tk.LEFT)
        ttk.Entry(job_row, textvariable=self._publication_year, width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(job_row, text="Job").pack(side=tk.LEFT)
        ttk.Entry(job_row, textvariable=self._job_id, width=16).pack(side=tk.LEFT, padx=4)

        review_row = ttk.Frame(meta_frame)
        review_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(review_row, text="Review PNG", variable=self._review_png).pack(side=tk.LEFT)
        ttk.Label(review_row, text="threshold").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(review_row, textvariable=self._review_conf_threshold, width=4).pack(side=tk.LEFT)

        # ── Secondary panels ──────────────────────────────────────────────
        sec = ttk.Frame(outer)
        sec.pack(fill=tk.X, pady=(0, 4))

        train_frame = ttk.LabelFrame(sec, text="Training loop", padding=4)
        train_frame.pack(side=tk.LEFT, fill=tk.Y)
        trow = ttk.Frame(train_frame)
        trow.pack(fill=tk.X)
        ttk.Button(trow, text="Open corrected", command=self._open_corrected).pack(side=tk.LEFT)
        ttk.Button(trow, text="Teach", command=self._teach).pack(side=tk.LEFT, padx=4)
        ttk.Label(train_frame, textvariable=self._rules_count, foreground=_MUTED).pack(anchor=tk.W, pady=(2, 0))

        comp_frame = ttk.LabelFrame(sec, text="Companions", padding=4)
        comp_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        for name, installed, hint in _companion_status():
            color = _MUTED if installed else "#aa3300"
            text = f"✓ {name}" if installed else f"✗ {name}"
            ttk.Label(comp_frame, text=text, foreground=color).pack(anchor=tk.W)

        # ── Status + log ─────────────────────────────────────────────────
        ttk.Label(outer, textvariable=self._status, foreground=_MUTED).pack(anchor=tk.W)
        log_frame = ttk.LabelFrame(outer, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self._log = scrolledtext.ScrolledText(
            log_frame, height=6, bg=_FIELD_BG, fg=_FG, state=tk.DISABLED, wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True)

    def _on_api_key_change(self) -> None:
        provider = detect_provider(self._api_key.get())
        self._provider_label.set(f"Provider: {provider_label(provider)}")

    def _refresh_rules_count(self) -> None:
        n = tune_rule_count()
        self._rules_count.set(f"{n} rule{'s' if n != 1 else ''} learned")

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
            filetypes=[("Images/PDF", "*.pdf *.tif *.tiff *.jpg *.jpeg *.png"), ("All", "*.*")],
        )
        for p in paths:
            self._add_path(Path(p))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder of images or PDFs")
        if not folder:
            return
        folder_path = Path(folder)
        added = 0
        for p in sorted(folder_path.iterdir()):
            if p.is_file() and p.suffix.lower() in _INPUT_SUFFIXES:
                self._add_path(p)
                added += 1
        if added == 0:
            messagebox.showinfo("Historical OCR", f"No supported files found in {folder_path.name}.")

    def _add_url(self) -> None:
        url = self._url_var.get().strip()
        if not url:
            return
        if url in self._url_sources:
            messagebox.showinfo("Historical OCR", "URL already added.")
            return
        self._url_sources.append(url)
        self._files_list.insert(tk.END, f"[url] {url}")
        self._url_var.set("")

    def _clear_files(self) -> None:
        self._sources.clear()
        self._url_sources.clear()
        self._files_list.delete(0, tk.END)

    def _open_job(self) -> None:
        if self._last_job_root and self._last_job_root.is_dir():
            if sys.platform == "darwin":
                subprocess.run(["open", str(self._last_job_root / "export")], check=False)
            else:
                webbrowser.open((self._last_job_root / "export").as_uri())
        else:
            messagebox.showinfo("Historical OCR", "Run a job first.")

    def _open_corrected(self) -> None:
        job = self._last_job_id or self._job_id.get().strip()
        path = correction_template_path(job, self._settings)
        if not path:
            messagebox.showinfo(
                "Historical OCR",
                f"No export yet for job “{job}”. Run OCR first (step 1).",
            )
            return
        if sys.platform == "darwin":
            subprocess.run(["open", "-t", str(path)], check=False)
        else:
            webbrowser.open(path.as_uri())

    def _teach(self) -> None:
        job = self._last_job_id or self._job_id.get().strip()
        if not job:
            messagebox.showerror("Historical OCR", "No job to teach from.")
            return

        def _work() -> None:
            try:
                stats = teach_from_job(job, settings=self._settings, log_fn=self._log_q.put)
                self.root.after(0, lambda: self._rules_count.set(f"{stats['rules']} rules learned"))
                self.root.after(0, lambda: self._status.set("Teach complete."))
            except Exception as exc:
                self._log_q.put(f"teach error: {exc}")
                self.root.after(0, lambda: self._status.set("Teach failed."))

        threading.Thread(target=_work, daemon=True).start()
        self._status.set("Teaching…")

    def _start_run(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showwarning("Historical OCR", "Already running.")
            return
        job_id = self._job_id.get().strip()
        if not job_id:
            messagebox.showerror("Historical OCR", "Job name required.")
            return
        if not self._sources and not self._url_sources:
            messagebox.showerror("Historical OCR", "Add at least one file or URL.")
            return

        self._run_btn.configure(state=tk.DISABLED)
        self._status.set("Running…")
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    def _run_worker(self) -> None:
        try:
            tier: QualityTier = self._quality.get()  # type: ignore[assignment]
            api_key = self._api_key.get().strip() or None
            year = int(self._publication_year.get()) if self._publication_year.get().strip().isdigit() else None

            settings, provider, effective = apply_quality_tier(
                self._settings,
                tier,
                api_key=api_key,
            )
            if effective != tier:
                self._log_q.put(f"note: High needs an API key — using {effective} instead.")

            flags = tier_run_flags(effective)
            review_thr = 65.0
            if self._review_conf_threshold.get().strip().replace(".", "", 1).isdigit():
                review_thr = float(self._review_conf_threshold.get().strip())
            settings = settings.model_copy(
                update={
                    "symbol_glyph_heatmap": self._review_png.get(),
                    "review_conf_threshold": max(0.0, min(100.0, review_thr)),
                },
            )
            manifest = run_job(
                self._job_id.get().strip(),
                inputs=self._sources or None,
                urls=self._url_sources or None,
                settings=settings,
                mode="print",
                publication_year=year,
                clean=True,
                log_fn=self._log_q.put,
                **flags,
            )
            job_id = manifest.job_id
            self._last_job_id = job_id
            self._last_job_root = (settings.jobs_dir / job_id).expanduser().resolve()
            corr = correction_template_path(job_id, settings)
            if corr:
                self._log_q.put(f"step 2: edit {corr}")
            self._log_q.put(json.dumps(manifest.export, indent=2))
            ok_pages = sum(1 for p in manifest.pages if p.status == "ok")
            self._log_q.put(f"\n✓ Done — {ok_pages} page(s) · {effective} tier")
            self.root.after(0, lambda: self._status.set(f"✓ Done — {ok_pages} page(s), {effective} tier"))
        except Exception as exc:
            self._log_q.put(f"\n✗ Failed: {exc}")
            self.root.after(0, lambda: self._status.set("✗ Failed — see log"))
        finally:
            self.root.after(0, lambda: self._run_btn.configure(state=tk.NORMAL))

    def _state_dict(self) -> dict:
        return {
            "version": _STATE_VERSION,
            "job_id": self._job_id.get(),
            "api_key": self._api_key.get(),
            "quality": self._quality.get(),
            "review_png": self._review_png.get(),
            "review_conf_threshold": self._review_conf_threshold.get(),
            "publication_year": self._publication_year.get(),
            "sources": [str(p) for p in self._sources],
            "url_sources": list(self._url_sources),
            "last_job_id": self._last_job_id,
        }

    def _load_state(self) -> None:
        data = load_gui_state()
        if not data or int(data.get("version", 0)) != _STATE_VERSION:
            return
        self._job_id.set(str(data.get("job_id", self._job_id.get())))
        self._api_key.set(str(data.get("api_key", "")))
        self._quality.set(str(data.get("quality", "medium")))
        self._review_png.set(bool(data.get("review_png", True)))
        self._review_conf_threshold.set(str(data.get("review_conf_threshold", "65")))
        self._publication_year.set(str(data.get("publication_year", "1970")))
        self._last_job_id = data.get("last_job_id")
        for raw in data.get("sources", []):
            path = Path(str(raw))
            if path.is_file():
                self._add_path(path)
        for u in data.get("url_sources", []):
            if u and u not in self._url_sources:
                self._url_sources.append(u)
                self._files_list.insert(tk.END, f"[url] {u}")

    def _on_close(self) -> None:
        try:
            save_gui_state(self._state_dict())
        except OSError:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.update_idletasks()
        self.root.mainloop()


def main() -> None:
    HistoricalOcrGui().run()


if __name__ == "__main__":
    main()
