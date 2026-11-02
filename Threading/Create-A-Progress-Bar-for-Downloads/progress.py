"""Terminal progress-bar rendering used by the threaded downloader.

The bar is deliberately dumb: it is driven entirely from the main thread,
which receives byte-count snapshots from the download worker.  Keeping all
terminal writes on one thread avoids interleaved output and mirrors the way a
UI thread marshals delegate callbacks in event-driven frameworks.
"""

from __future__ import annotations

import sys
import time
from typing import TextIO


def human_bytes(value: float) -> str:
    """Return a compact binary-unit string such as ``1.50 MiB``."""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{amount:.0f} B"
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{amount:.2f} TiB"


def human_time(seconds: float | None) -> str:
    """Format a duration as ``MM:SS`` or ``H:MM:SS``; ``--:--`` if unknown."""
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "--:--"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ProgressBar:
    """Render download progress to a text stream.

    On a TTY the bar redraws in place with ``\\r``; on a pipe it emits one
    line per 10 % step, which keeps logs and captured demo output readable.
    """

    def __init__(
        self,
        label: str = "download",
        *,
        stream: TextIO | None = None,
        width: int = 30,
        enabled: bool = True,
        force_lines: bool = False,
    ) -> None:
        self.label = label
        self.stream: TextIO = stream if stream is not None else sys.stderr
        self.width = max(10, width)
        self.enabled = enabled
        self._tty = False if force_lines else bool(
            getattr(self.stream, "isatty", lambda: False)()
        )
        self._start = time.monotonic()
        self._initial = 0
        self._last_time = self._start
        self._last_bytes = 0
        self._rate = 0.0
        self._done = 0
        self._total: int | None = None
        self._bucket = -1
        self._closed = False

    def start(self, done: int = 0, total: int | None = None) -> None:
        """Reset the timer, optionally starting from a resumed byte offset."""
        self._start = time.monotonic()
        self._initial = done
        self._last_time = self._start
        self._last_bytes = done
        self._rate = 0.0
        self._done = done
        self._total = total
        self._bucket = -1

    def update(self, done: int, total: int | None) -> None:
        """Feed a new absolute byte count and redraw if due."""
        if not self.enabled or self._closed:
            return
        self._done = done
        self._total = total
        now = time.monotonic()
        delta_time = now - self._last_time
        if delta_time >= 0.05:
            instant = (done - self._last_bytes) / delta_time
            self._rate = instant if self._rate <= 0 else 0.3 * instant + 0.7 * self._rate
            self._last_time = now
            self._last_bytes = done
        self._emit(done, total)

    def finish(self) -> None:
        """Draw the final state and terminate the line."""
        if not self.enabled or self._closed:
            return
        if self._tty:
            self.stream.write("\r" + self._render(self._done, self._total) + "\n")
        else:
            self._emit(self._done, self._total)
        self.stream.flush()
        self._closed = True

    def clear(self) -> None:
        """Erase the current TTY line before printing a notice."""
        if self.enabled and self._tty and not self._closed:
            self.stream.write("\r" + " " * 100 + "\r")
            self.stream.flush()

    def _emit(self, done: int, total: int | None) -> None:
        line = self._render(done, total)
        if self._tty:
            self.stream.write("\r" + line)
            self.stream.flush()
            return
        percent = (done / total * 100.0) if total else None
        bucket = int(percent // 10) if percent is not None else int(done // (1024 * 1024))
        if bucket != self._bucket:
            self.stream.write(line + "\n")
            self.stream.flush()
            self._bucket = bucket

    def _render(self, done: int, total: int | None) -> str:
        elapsed = max(time.monotonic() - self._start, 0.05)
        transferred = max(done - self._initial, 0)
        average = transferred / elapsed
        display_rate = self._rate if self._rate > 0 else average
        label = f"{self.label:<14}"
        if total:
            percent = min(100.0, done / total * 100.0)
            filled = int(self.width * percent / 100.0)
            bar = "#" * filled + "-" * (self.width - filled)
            remaining = max(total - done, 0)
            eta = remaining / average if average > 0 else None
            return (
                f"{label} [{bar}] {percent:5.1f}% "
                f"{human_bytes(done)}/{human_bytes(total)} "
                f"{human_bytes(display_rate)}/s ETA {human_time(eta)}"
            )
        return f"{label} {human_bytes(done)} downloaded  {human_bytes(display_rate)}/s"
