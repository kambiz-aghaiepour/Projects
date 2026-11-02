"""Download worker and main-thread driver for the progress-bar demo.

The worker thread owns the socket and the file handle; it publishes immutable
events on a bounded queue.  :func:`download` consumes those events on the
calling thread, which is therefore the only thread that renders progress.
"""

from __future__ import annotations

import hashlib
import queue
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from progress import ProgressBar

CHUNK_SIZE = 64 * 1024
USER_AGENT = "threaded-progress-bar/1.0"


@dataclass
class ProgressEvent:
    """Immutable message posted by the download thread to the main thread."""

    kind: str  # start | progress | notice | done | interrupted | cancelled | error
    done: int = 0
    total: int | None = None
    message: str = ""
    sha256: str = ""


@dataclass
class DownloadResult:
    """Outcome of one download attempt."""

    status: str  # completed | interrupted | cancelled | error
    path: Path | None
    bytes_written: int
    total: int | None
    sha256: str = ""
    error: str = ""
    resumed_from: int = 0


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Downloader(threading.Thread):
    """Worker thread that downloads ``url`` into ``destination``.

    Progress events are pushed onto ``events``; the thread never writes to
    stdout/stderr itself.
    """

    def __init__(
        self,
        url: str,
        destination: Path,
        events: queue.Queue[ProgressEvent],
        *,
        resume: bool = False,
        chunk_size: int = CHUNK_SIZE,
        timeout: float = 20.0,
        interrupt_after: int | None = None,
    ) -> None:
        super().__init__(name="downloader", daemon=True)
        self.url = url
        self.destination = destination
        self.events = events
        self.resume = resume
        self.chunk_size = max(1024, chunk_size)
        self.timeout = timeout
        self.interrupt_after = interrupt_after
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Ask the worker to stop at the next chunk boundary."""
        self._cancel.set()

    def run(self) -> None:
        try:
            self._download()
        except Exception as exc:  # surfaced to the renderer, never raised here
            self.events.put(
                ProgressEvent("error", message=f"{type(exc).__name__}: {exc}")
            )

    def _emit(self, kind: str, done: int = 0, total: int | None = None, **kwargs: str) -> None:
        self.events.put(ProgressEvent(kind, done, total, **kwargs))

    def _download(self) -> None:
        destination = Path(self.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(destination.name + ".part")

        offset = part.stat().st_size if self.resume and part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if offset:
            headers["Range"] = f"bytes={offset}-"

        request = urllib.request.Request(self.url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset:
                raise OSError(
                    f"server rejected resume offset {offset:,}; "
                    f"delete {part.name} and retry"
                ) from exc
            raise

        with response:
            status = response.getcode()
            if offset and status != 206:
                offset = 0
                self._emit(
                    "notice",
                    message="server ignored the Range request; restarting from byte 0",
                )
            total = self._total_size(response, status, offset)

            mode = "ab" if offset else "wb"
            done = offset
            self._emit("start", done, total)
            with open(part, mode) as handle:
                while True:
                    if self._cancel.is_set():
                        self._emit("cancelled", done, total, message=f"stopped at {done:,} bytes")
                        return
                    chunk = response.read(self.chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    self._emit("progress", done, total)
                    if self.interrupt_after is not None and done >= self.interrupt_after:
                        self._emit(
                            "interrupted",
                            done,
                            total,
                            message=f"connection dropped after {done:,} bytes",
                        )
                        return

        if total is not None and done != total:
            raise OSError(f"incomplete transfer: expected {total:,} bytes, received {done:,}")

        part.replace(destination)
        digest = sha256_file(destination)
        self._emit("done", done, total, message=str(destination), sha256=digest)

    @staticmethod
    def _total_size(response, status: int, offset: int) -> int | None:
        if status == 206:
            content_range = response.headers.get("Content-Range", "")
            _, _, total_part = content_range.partition("/")
            if total_part.strip().isdigit():
                return int(total_part)
        length = response.headers.get("Content-Length")
        if length and length.isdigit():
            return offset + int(length) if status == 206 else int(length)
        return None


def download(
    url: str,
    destination: Path,
    *,
    resume: bool = False,
    quiet: bool = False,
    chunk_size: int = CHUNK_SIZE,
    timeout: float = 20.0,
    stream: TextIO | None = None,
    interrupt_after: int | None = None,
    label: str = "download",
) -> DownloadResult:
    """Run one download while rendering progress on the calling thread."""
    output: TextIO = stream if stream is not None else sys.stderr
    events: queue.Queue[ProgressEvent] = queue.Queue(maxsize=256)
    worker = Downloader(
        url,
        Path(destination),
        events,
        resume=resume,
        chunk_size=chunk_size,
        timeout=timeout,
        interrupt_after=interrupt_after,
    )
    bar = ProgressBar(label, stream=output, enabled=not quiet)
    result = DownloadResult("error", None, 0, None, error="download did not start")
    resumed_from = 0
    bar_started = False
    worker.start()

    try:
        while True:
            event = events.get()
            if event.kind == "start":
                bar.start(event.done, event.total)
                bar_started = True
                resumed_from = event.done
                if event.done and not quiet:
                    bar.clear()
                    output.write(f"  resuming at byte {event.done:,}\n")
                    output.flush()
            elif event.kind == "progress":
                bar.update(event.done, event.total)
            elif event.kind == "notice":
                bar.clear()
                output.write(f"  note: {event.message}\n")
                output.flush()
            elif event.kind == "done":
                bar.finish()
                result = DownloadResult(
                    "completed",
                    Path(destination),
                    event.done,
                    event.total,
                    sha256=event.sha256,
                    resumed_from=resumed_from,
                )
                break
            elif event.kind == "interrupted":
                bar.finish()
                result = DownloadResult(
                    "interrupted",
                    Path(str(destination) + ".part"),
                    event.done,
                    event.total,
                    error=event.message,
                )
                break
            elif event.kind == "cancelled":
                bar.finish()
                result = DownloadResult("cancelled", None, event.done, event.total, error=event.message)
                break
            else:  # error
                if bar_started:
                    bar.finish()
                result = DownloadResult("error", None, 0, None, error=event.message)
                break
    except KeyboardInterrupt:
        worker.cancel()
        bar.clear()
        output.write("\n  interrupted by user; partial data kept for --resume\n")
        output.flush()
        result = DownloadResult("cancelled", None, 0, None, error="cancelled by user")
    finally:
        worker.join(timeout=5)
    return result
