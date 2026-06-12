"""Tests for job progress tracking."""

from __future__ import annotations

import io
import sys

from historical_ocr.lib.job_progress import (
    JobProgress,
    cli_progress_sink,
    format_duration,
    parse_progress_line,
    wrap_log_fn,
)


def test_format_duration():
    assert format_duration(0.2) == "<1s"
    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(120) == "2m"
    assert format_duration(3665) == "1h 1m"


def test_page_stats_increments_done_and_eta():
    p = JobProgress()
    p.set_stage("ocr", total=4)
    assert p.consume_log("page-stats: page=p0001 10.0s lines=100 conf=90.0")
    assert p.done == 1
    assert len(p._page_durations) == 1
    p.consume_log("page-stats: page=p0002 20.0s lines=80 conf=85.0")
    line = p.format_line()
    assert "ocr 2/4 50%" in line
    assert "left" in line
    assert "elapsed" in line


def test_clean_parsing():
    p = JobProgress()
    p.set_stage("clean", total=2)
    assert p.consume_log("clean: p0001 (Underwood rules)")
    assert p.done == 1
    assert not p.consume_log("page-stats: page=p0001 10.0s lines=1 conf=90.0")
    assert p.done == 1


def test_wrap_log_fn_emits_progress():
    p = JobProgress()
    p.set_stage("ocr", total=2)
    lines: list[str] = []
    wrapped = wrap_log_fn(lines.append, p)
    wrapped("page-stats: page=p0001 5.0s lines=10 conf=90.0")
    assert any(l.startswith("progress: ocr") for l in lines)
    assert any("page-stats:" in l for l in lines)


def test_parse_progress_line():
    parsed = parse_progress_line("progress: ocr 3/8 38% · ~2m left · 1m elapsed")
    assert parsed == {"stage": "ocr", "done": 3, "total": 8, "pct": 38}


def test_cli_progress_sink_non_tty(capsys):
    sink = cli_progress_sink()
    sink("progress: ocr 1/2 50% · 5s elapsed")
    sink("hello")
    sink.finalize()
    err = capsys.readouterr().err
    assert "progress: ocr" in err
    assert "hello" in err


def test_cli_progress_sink_tty(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "write", buf.write)
    monkeypatch.setattr(sys.stderr, "flush", lambda: None)
    sink = cli_progress_sink()
    sink("progress: ocr 1/2 50% · 5s elapsed")
    assert "\r\033[Kprogress:" in buf.getvalue()
    sink("log line")
    assert "\n" in buf.getvalue()
    sink.finalize()
