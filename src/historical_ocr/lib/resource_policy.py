"""Power-aware concurrency and background-friendly tuning (via strigil.hardware)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from historical_ocr.config import Settings

_sleep_inhibitor: subprocess.Popen | None = None


def prevent_sleep() -> None:
    """Prevent the OS from suspending the process mid-job (lid close / idle).

    - macOS: spawns `caffeinate -i -w <pid>` (system idle-sleep assertion)
    - Linux: spawns `systemd-inhibit --what=sleep:idle` wrapping this process
    - Windows/other: no-op (process priority is handled separately)
    """
    global _sleep_inhibitor
    if _sleep_inhibitor is not None:
        return
    try:
        if sys.platform == "darwin":
            _sleep_inhibitor = subprocess.Popen(
                ["caffeinate", "-i", "-w", str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform.startswith("linux"):
            _sleep_inhibitor = subprocess.Popen(
                [
                    "systemd-inhibit",
                    "--what=sleep:idle",
                    "--who=historical-ocr",
                    "--why=OCR job in progress",
                    "--mode=block",
                    "sleep", "infinity",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (FileNotFoundError, OSError):
        pass


def allow_sleep() -> None:
    """Release the sleep inhibitor after a job completes."""
    global _sleep_inhibitor
    if _sleep_inhibitor is not None:
        _sleep_inhibitor.terminate()
        _sleep_inhibitor = None


def _linux_battery_percent() -> int | None:
    """Read battery level from sysfs when strigil is not available."""
    import glob

    for path in glob.glob("/sys/class/power_supply/BAT*/capacity"):
        try:
            return int(open(path).read().strip())
        except (OSError, ValueError):
            pass
    return None


def _linux_is_ac_power() -> bool | None:
    """Return True if on AC, False if on battery, None if unknown."""
    import glob

    for path in glob.glob("/sys/class/power_supply/AC*/online"):
        try:
            return open(path).read().strip() == "1"
        except (OSError, ValueError):
            pass
    # Fallback: no battery present means we're on AC
    if glob.glob("/sys/class/power_supply/BAT*"):
        return None  # battery exists but couldn't read AC state
    return True  # no battery at all — desktop / always-on

_OCR_WORKERS = {
    "conservative": 1,
    "balanced": 2,
    "aggressive": 4,
}


def _hardware_api() -> tuple[Callable, Callable, Callable, Callable, Callable] | None:
    try:
        from strigil.hardware import (
            battery_percent,
            detect_hardware,
            is_ac_power,
            suggest_aggressiveness,
        )

        return (
            detect_hardware,
            suggest_aggressiveness,
            is_ac_power,
            battery_percent,
            lambda: None,  # placeholder for format_hardware if needed
        )
    except ImportError:
        return None


def resolve_parallel_pages(settings: Settings) -> int:
    """Cap page parallelism from power state and background mode.

    Also sets OMP_THREAD_LIMIT so Tesseract doesn't oversubscribe when
    multiple pages are running in parallel.
    """
    requested = max(1, int(settings.parallel_pages))
    if not settings.power_aware and not settings.background_mode:
        workers = requested
    else:
        api = _hardware_api()
        if api is None:
            workers = 1 if settings.background_mode else requested
        else:
            detect_hardware, suggest_aggressiveness, _, _, _ = api
            hw = detect_hardware()
            if settings.background_mode:
                preset = "conservative"
            else:
                preset = suggest_aggressiveness(hw)

            cap = _OCR_WORKERS.get(preset, 1)
            if preset == "aggressive":
                cpu = int(hw.get("cpu_count") or 1)
                cap = min(max(2, cpu // 2), 4)
            workers = max(1, min(requested, cap))

    # Prevent Tesseract from spawning unlimited OpenMP threads per worker,
    # which would saturate all cores when parallel_pages > 1.
    if workers > 1:
        import multiprocessing

        cpu_count = multiprocessing.cpu_count()
        omp_limit = str(max(1, cpu_count // workers))
        os.environ.setdefault("OMP_THREAD_LIMIT", omp_limit)
        os.environ.setdefault("OMP_NUM_THREADS", omp_limit)

    return workers


def apply_background_priority() -> None:
    """Lower process priority so OCR stays in the background on a laptop."""
    try:
        if sys.platform == "win32":
            import ctypes

            below_normal = 0x00004000
            proc = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(proc, below_normal)
        else:
            os.nice(10)
    except (OSError, AttributeError, PermissionError):
        pass


def yield_between_pages(settings: Settings) -> None:
    """Brief pause between pages when on battery or in background mode."""
    if not settings.power_aware and not settings.background_mode:
        return
    api = _hardware_api()
    if api is None:
        # strigil not available — use sysfs on Linux, fixed delay otherwise
        if sys.platform.startswith("linux"):
            on_ac = _linux_is_ac_power()
            if settings.background_mode or on_ac is False:
                pct = _linux_battery_percent()
                time.sleep(1.0 if pct is not None and pct < 20 else 0.35)
        elif settings.background_mode:
            time.sleep(0.25)
        return
    _, _, is_ac_power, battery_percent, _ = api
    on_ac = is_ac_power()
    if settings.background_mode or on_ac is False:
        pct = battery_percent()
        time.sleep(1.0 if pct is not None and pct < 20 else 0.35)


def resource_status_line(settings: Settings) -> str | None:
    """Short power/parallelism summary for logs."""
    api = _hardware_api()
    workers = resolve_parallel_pages(settings)
    if api is None:
        # strigil not available — use sysfs on Linux for power state
        if sys.platform.startswith("linux"):
            on_ac = _linux_is_ac_power()
            pct = _linux_battery_percent()
            if on_ac is True:
                power = "AC"
            elif on_ac is False:
                power = f"battery {pct}%" if pct is not None else "battery"
            else:
                power = "unknown"
            preset = "conservative" if settings.background_mode else "balanced"
            return f"resource: {power} · {preset} · {workers} page worker(s)"
        if settings.background_mode:
            return f"resource: background mode · {workers} page worker(s)"
        return None
    _, suggest_aggressiveness, is_ac_power, battery_percent, _ = api
    preset = "conservative" if settings.background_mode else suggest_aggressiveness()
    on_ac = is_ac_power()
    pct = battery_percent()
    if on_ac is True:
        power = "AC"
    elif on_ac is False:
        power = f"battery {pct}%" if pct is not None else "battery"
    else:
        power = "unknown"
    return f"resource: {power} · {preset} · {workers} page worker(s)"
