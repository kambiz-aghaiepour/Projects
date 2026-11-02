"""Bounded two-stage thumbnail pipeline built on ``concurrent.futures``.

Stage 1 is a fixed-size ``ThreadPoolExecutor`` that decodes, auto-orients,
resizes and re-encodes images into a staging directory.  Stage 2 is a single
renamer thread that assigns final, collision-free names from a template and
attaches metadata (EXIF capture date, dimensions, sizes, SHA-256) before
writing a JSON manifest.

The producer is throttled with a bounded semaphore so at most
``2 * workers`` resize jobs are in flight, and the hand-off queue between the
stages is bounded as well.  A slow renamer therefore applies backpressure
instead of letting hundreds of decoded images pile up in memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageOps

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".webp",
}
FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def discover_images(root: Path, recursive: bool = True) -> list[Path]:
    """Return supported image files under ``root`` in stable sorted order."""
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: path.as_posix().lower(),
    )


def safe_component(value: str) -> str:
    """Reduce an arbitrary string to a safe file-name component."""
    cleaned = _UNSAFE.sub("_", value).strip("._-")
    return cleaned or "image"


def date_slug(captured: str | None) -> str:
    """Turn ``2024:05:01 09:30:00`` into ``2024-05-01`` for templates."""
    if not captured:
        return "unknown"
    digits = re.sub(r"[^0-9]", "", captured[:10])
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return "unknown"


def validate_template(template: str) -> None:
    """Raise ``ValueError`` if ``template`` cannot be formatted."""
    try:
        template.format(index=1, stem="photo", date="2024-01-01", width=120, height=90)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(f"invalid name template: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(256 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _capture_date(image: Image.Image) -> str | None:
    """Return EXIF DateTimeOriginal (or DateTime) if the file carries one."""
    try:
        exif = image.getexif()
    except Exception:
        return None
    for tag in (36867, 306):  # DateTimeOriginal, DateTime
        value = exif.get(tag)
        if isinstance(value, bytes):
            value = value.decode("ascii", "ignore")
        if value:
            text = str(value).strip().strip("\x00")
            if text:
                return text
    return None


@dataclass(frozen=True)
class Job:
    """One source image plus its stable discovery ordinal."""

    ordinal: int
    source: Path


@dataclass
class Thumbnail:
    """Successful stage-1 result waiting to be renamed by stage 2."""

    job: Job
    staged: Path
    width: int
    height: int
    source_width: int
    source_height: int
    source_bytes: int
    captured: str | None


@dataclass
class Failure:
    """A per-file error that must not abort the batch."""

    source: Path
    stage: str
    error: str


@dataclass
class Stats:
    discovered: int = 0
    resized: int = 0
    renamed: int = 0
    failed: int = 0
    input_bytes: int = 0
    output_bytes: int = 0


@dataclass
class Summary:
    """Final report returned by :meth:`ThumbnailPipeline.wait`."""

    discovered: int
    resized: int
    renamed: int
    failed: int
    input_bytes: int
    output_bytes: int
    elapsed: float
    output_dir: Path
    manifest_path: Path
    entries: list[dict]
    failures: list[Failure]
    settings: dict


class ThumbnailPipeline:
    """Run resize workers and a renamer over ``sources`` without blocking."""

    def __init__(
        self,
        sources: Sequence[Path],
        output_dir: Path,
        *,
        input_root: Path | None = None,
        size: tuple[int, int] = (200, 200),
        workers: int = 4,
        image_format: str = "JPEG",
        quality: int = 85,
        name_template: str = "{stem}_thumb",
        report_path: Path | None = None,
    ) -> None:
        validate_template(name_template)
        if image_format not in FORMAT_EXTENSIONS:
            raise ValueError(f"unsupported format: {image_format}")
        if not (1 <= workers <= 32):
            raise ValueError("workers must be between 1 and 32")
        if not (1 <= quality <= 100):
            raise ValueError("quality must be between 1 and 100")
        if size[0] < 1 or size[1] < 1:
            raise ValueError("thumbnail dimensions must be positive")

        self.sources = list(sources)
        self.output_dir = Path(output_dir)
        self.input_root = Path(input_root) if input_root else None
        self.size = (int(size[0]), int(size[1]))
        self.workers = workers
        self.image_format = image_format
        self.quality = quality
        self.name_template = name_template
        self.manifest_path = Path(report_path) if report_path else self.output_dir / "manifest.json"
        self.staging = self.output_dir / ".staging"

        self.entries: list[dict] = []
        self.failures: list[Failure] = []
        self._used_names: set[str] = set()
        self._stats = Stats()
        self._lock = threading.Lock()
        self._report_lock = threading.Lock()
        self._summary: Summary | None = None
        self._done = threading.Event()
        self._started = False
        self._started_at = 0.0

        self._slots = threading.BoundedSemaphore(max(2, workers * 2))
        self._handoff: queue.Queue[Thumbnail | Failure | None] = queue.Queue(
            maxsize=max(2, workers * 2)
        )
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="resize")
        self._producer: threading.Thread | None = None
        self._renamer: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start the producer, resize pool and renamer; returns immediately."""
        if self._started:
            raise RuntimeError("pipeline already started")
        self._started = True
        self._started_at = time.monotonic()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)
        self._renamer = threading.Thread(target=self._rename_loop, name="rename", daemon=True)
        self._renamer.start()
        self._producer = threading.Thread(target=self._produce, name="producer", daemon=True)
        self._producer.start()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def wait(self) -> Summary:
        """Block until both stages finish and return the summary."""
        if not self._started:
            raise RuntimeError("pipeline has not been started")
        self._done.wait()
        if self._producer:
            self._producer.join(timeout=5)
        if self._renamer:
            self._renamer.join(timeout=5)
        with self._report_lock:
            if self._summary is None:
                elapsed = time.monotonic() - self._started_at
                self._write_manifest(elapsed)
                stats = self.stats()
                self._summary = Summary(
                    discovered=stats.discovered,
                    resized=stats.resized,
                    renamed=stats.renamed,
                    failed=stats.failed,
                    input_bytes=stats.input_bytes,
                    output_bytes=stats.output_bytes,
                    elapsed=elapsed,
                    output_dir=self.output_dir,
                    manifest_path=self.manifest_path,
                    entries=sorted(self.entries, key=lambda item: item["index"]),
                    failures=list(self.failures),
                    settings={
                        "width": self.size[0],
                        "height": self.size[1],
                        "workers": self.workers,
                        "format": self.image_format,
                        "quality": self.quality,
                        "name_template": self.name_template,
                    },
                )
        return self._summary

    def stats(self) -> Stats:
        """Return a consistent snapshot of the counters."""
        with self._lock:
            return replace(self._stats)

    def _bump(self, **deltas: int) -> None:
        with self._lock:
            for field, delta in deltas.items():
                setattr(self._stats, field, getattr(self._stats, field) + delta)

    # -- stage 0: producer -------------------------------------------------

    def _produce(self) -> None:
        try:
            for ordinal, source in enumerate(self.sources, start=1):
                self._bump(discovered=1)
                self._slots.acquire()
                future = self._pool.submit(self._resize_one, Job(ordinal, Path(source)))
                future.add_done_callback(self._collect)
        finally:
            self._pool.shutdown(wait=True)
            self._handoff.put(None)

    def _collect(self, future) -> None:
        """Bridge a completed resize future into the bounded hand-off queue."""
        try:
            item: Thumbnail | Failure = future.result()
        except Exception as exc:  # defensive: _resize_one should not raise
            item = Failure(Path("<unknown>"), "resize", f"{type(exc).__name__}: {exc}")
        self._handoff.put(item)
        self._slots.release()

    # -- stage 1: resize ---------------------------------------------------

    def _resize_one(self, job: Job) -> Thumbnail | Failure:
        staged: Path | None = None
        try:
            source_bytes = job.source.stat().st_size
            with Image.open(job.source) as image:
                image.load()  # force decoding now so truncated files fail here
                source_width, source_height = image.size
                captured = _capture_date(image)
                picture = ImageOps.exif_transpose(image)
                if self.image_format == "JPEG" and picture.mode not in ("RGB", "L"):
                    picture = picture.convert("RGB")
                elif self.image_format == "WEBP" and picture.mode not in ("RGB", "RGBA", "L"):
                    picture = picture.convert("RGBA")
                picture.thumbnail(self.size, Image.Resampling.LANCZOS)
                width, height = picture.size
                staged = self.staging / f"{job.ordinal:05d}{FORMAT_EXTENSIONS[self.image_format]}"
                options: dict[str, object] = {}
                if self.image_format in ("JPEG", "WEBP"):
                    options["quality"] = self.quality
                picture.save(staged, format=self.image_format, **options)
        except Exception as exc:
            if staged is not None:
                staged.unlink(missing_ok=True)
            return Failure(job.source, "resize", f"{type(exc).__name__}: {exc}")

        self._bump(resized=1, input_bytes=source_bytes)
        return Thumbnail(
            job=job,
            staged=staged,
            width=width,
            height=height,
            source_width=source_width,
            source_height=source_height,
            source_bytes=source_bytes,
            captured=captured,
        )

    # -- stage 2: rename + metadata ---------------------------------------

    def _rename_loop(self) -> None:
        while True:
            item = self._handoff.get()
            if item is None:
                break
            if isinstance(item, Failure):
                self._record_failure(item)
                continue
            self._finish_one(item)
        self._done.set()

    def _finish_one(self, item: Thumbnail) -> None:
        try:
            base = self.name_template.format(
                index=item.job.ordinal,
                stem=safe_component(item.job.source.stem),
                date=date_slug(item.captured),
                width=item.width,
                height=item.height,
            )
            destination = self._unique_destination(safe_component(base))
            os.replace(item.staged, destination)
            metadata = {
                "index": item.job.ordinal,
                "source": self._relative(item.job.source),
                "thumbnail": destination.name,
                "source_dimensions": [item.source_width, item.source_height],
                "thumbnail_dimensions": [item.width, item.height],
                "source_bytes": item.source_bytes,
                "thumbnail_bytes": destination.stat().st_size,
                "captured": item.captured,
                "sha256": _sha256(destination),
            }
        except Exception as exc:
            item.staged.unlink(missing_ok=True)
            self._record_failure(Failure(item.job.source, "rename", f"{type(exc).__name__}: {exc}"))
            return
        self.entries.append(metadata)
        self._bump(renamed=1, output_bytes=metadata["thumbnail_bytes"])

    def _record_failure(self, failure: Failure) -> None:
        self.failures.append(failure)
        self._bump(failed=1)

    def _unique_destination(self, base: str) -> Path:
        suffix = FORMAT_EXTENSIONS[self.image_format]
        candidate = self.output_dir / f"{base}{suffix}"
        counter = 1
        while candidate.exists() or candidate.name in self._used_names:
            candidate = self.output_dir / f"{base}-{counter}{suffix}"
            counter += 1
        self._used_names.add(candidate.name)
        return candidate

    def _relative(self, path: Path) -> str:
        if self.input_root is not None:
            try:
                return path.relative_to(self.input_root).as_posix()
            except ValueError:
                pass
        return path.name

    def _write_manifest(self, elapsed: float) -> None:
        stats = self.stats()
        payload = {
            "generator": "bulk-thumbnail-creator",
            "settings": {
                "max_width": self.size[0],
                "max_height": self.size[1],
                "format": self.image_format,
                "quality": self.quality,
                "workers": self.workers,
                "name_template": self.name_template,
            },
            "counts": {
                "discovered": stats.discovered,
                "resized": stats.resized,
                "renamed": stats.renamed,
                "failed": stats.failed,
            },
            "elapsed_seconds": round(elapsed, 3),
            "thumbnails": sorted(self.entries, key=lambda item: item["index"]),
            "failures": [
                {
                    "source": self._relative(failure.source),
                    "stage": failure.stage,
                    "error": failure.error,
                }
                for failure in self.failures
            ],
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            self.staging.rmdir()
        except OSError:
            pass  # leave the directory if an unexpected file remains
