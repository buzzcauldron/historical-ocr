"""Job progress tracking and ETA for CLI/GUI."""

from __future__ import annotations

import re
import sys
import time
from collections import deque
from typing import Callable, TextIO

_PAGE_STATS_RE = re.compile(
    r"^page-stats:\s+page=\S+\s+(?P<elapsed>\d+(?:\.\d+)?)s",
)
_CLEAN_RE = re.compile(r"^clean:\s+(\S+)")
_PROGRESS_RE = re.compile(
    r"^progress:\s+(?P<stage>\w+)\s+(?P<done>\d+)/(?P<total>\d+)\s+(?P<pct>\d+)%",
)

_STAGE_LABELS = {
    "acquire": "Acquire",
    "prepare": "Prepare",
    "ocr": "OCR",
    "clean": "Clean",
    "export": "Export",
    "done": "Done",
}


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return "<1s"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def parse_progress_line(msg: str) -> dict[str, int | str] | None:
    m = _PROGRESS_RE.match(msg.strip())
    if not m:
        return None
    return {
        "stage": m.group("stage"),
        "done": int(m.group("done")),
        "total": int(m.group("total")),
        "pct": int(m.group("pct")),
    }


class JobProgress:
    def __init__(self) -> None:
        self.stage = "prepare"
        self.done = 0
        self.total = 0
        self._job_start = time.monotonic()
        self._stage_start = self._job_start
        self._page_durations: deque[float] = deque(maxlen=16)
        self._last_line = ""
        self._seen_clean: set[str] = set()

    def set_stage(self, stage: str, total: int | None = None) -> None:
        if stage != self.stage:
            self.stage = stage
            self.done = 0
            self._stage_start = time.monotonic()
            if stage != "clean":
                self._seen_clean.clear()
        if total is not None:
            self.total = max(0, total)

    def consume_log(self, msg: str) -> bool:
        changed = False
        if msg.startswith("page-stats:") and self.stage == "ocr":
            m = _PAGE_STATS_RE.match(msg)
            if m:
                self.done += 1
                self._page_durations.append(float(m.group("elapsed")))
                changed = True
        elif msg.startswith("clean:") and self.stage == "clean":
            m = _CLEAN_RE.match(msg)
            if m and m.group(1) not in self._seen_clean:
                self._seen_clean.add(m.group(1))
                self.done += 1
                changed = True
        return changed

    def _pct(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, int(round(100 * self.done / self.total)))

    def _eta_seconds(self) -> float | None:
        if self.total <= 0 or self.done <= 0 or self.done >= self.total:
            return None
        if self._page_durations and self.stage == "ocr":
            avg = sum(self._page_durations) / len(self._page_durations)
            return avg * (self.total - self.done)
        elapsed = time.monotonic() - self._stage_start
        if self.done <= 0:
            return None
        return elapsed * (self.total - self.done) / self.done

    def format_line(self) -> str:
        label = _STAGE_LABELS.get(self.stage, self.stage.capitalize())
        pct = self._pct()
        elapsed = time.monotonic() - self._job_start
        if self.total > 0:
            parts = [f"progress: {self.stage} {self.done}/{self.total} {pct}%"]
            eta = self._eta_seconds()
            if eta is not None:
                parts.append(f"~{format_duration(eta)} left")
            parts.append(f"{format_duration(elapsed)} elapsed")
            return " · ".join(parts)
        return f"progress: {self.stage} 0/0 0% · {label}… · {format_duration(elapsed)} elapsed"

    def emit_if_changed(self, log_fn: Callable[[str], None]) -> None:
        line = self.format_line()
        if line != self._last_line:
            self._last_line = line
            log_fn(line)

    def finish(self, log_fn: Callable[[str], None]) -> None:
        self.set_stage("done", total=1)
        self.done = 1
        self._last_line = ""
        log_fn(self.format_line())


def wrap_log_fn(
    log_fn: Callable[[str], None],
    progress: JobProgress,
) -> Callable[[str], None]:
    def _wrapped(msg: str) -> None:
        if progress.consume_log(msg):
            progress.emit_if_changed(log_fn)
        log_fn(msg)

    def set_stage(stage: str, total: int | None = None) -> None:
        progress.set_stage(stage, total=total)
        progress.emit_if_changed(log_fn)

    _wrapped.set_stage = set_stage  # type: ignore[attr-defined]
    _wrapped.progress = progress  # type: ignore[attr-defined]
    return _wrapped


class CliProgressSink:
    """CLI log sink that overwrites a single progress line on TTY stderr."""

    def __init__(
        self,
        base_log_fn: Callable[[str], None] | None = None,
        *,
        stream: TextIO | None = None,
    ) -> None:
        self._base = base_log_fn
        self._stream = stream if stream is not None else sys.stderr
        self._is_tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._progress_active = False

    def __call__(self, msg: str) -> None:
        if msg.startswith("progress:"):
            if self._is_tty:
                self._stream.write(f"\r\033[K{msg}")
                self._stream.flush()
                self._progress_active = True
            elif self._base:
                self._base(msg)
            else:
                print(msg, file=self._stream, flush=True)
            return
        if self._progress_active and self._is_tty:
            self._stream.write("\n")
            self._progress_active = False
        if self._base:
            self._base(msg)
        else:
            print(msg, file=self._stream, flush=True)

    def finalize(self) -> None:
        if self._progress_active and self._is_tty:
            self._stream.write("\n")
            self._stream.flush()
            self._progress_active = False


def cli_progress_sink(
    base_log_fn: Callable[[str], None] | None = None,
) -> CliProgressSink:
    return CliProgressSink(base_log_fn)
