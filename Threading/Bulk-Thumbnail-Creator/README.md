# Bulk Thumbnail Creator

*Category: `Threading` — project directory: `Threading/Bulk-Thumbnail-Creator/`.*

## Problem

Create an image program which can take hundreds of images and convert them to
a specified size in a background thread while you do other things. For added
complexity, have one thread handling resizing and another bulk renaming of
thumbnails.

## Features

- **Two-stage pipeline** — a bounded pool of resize workers decodes,
  auto-orients and shrinks images into a staging area; a separate renamer
  thread assigns final names and collects metadata.
- **Non-blocking API** — `ThumbnailPipeline.start()` returns immediately, so
  the main thread can keep working (the CLI uses it to show a live status
  line; the demo uses it to poll progress).
- **Bounded backpressure** — at most `2 × workers` resize jobs are in flight,
  and the hand-off queue between the stages is bounded. A slow disk cannot
  make the process accumulate hundreds of decoded images in memory.
- **Failure isolation** — corrupt, truncated, missing or unreadable images are
  recorded with the failing stage and error, while the rest of the batch
  completes. `--strict` turns any failure into exit code 1.
- **Deterministic naming** — `--name-template` supports `{index}`, `{stem}`,
  `{date}`, `{width}` and `{height}`; collisions get `-1`, `-2`, … suffixes.
- **Metadata manifest** — every thumbnail records source path, dimensions,
  byte sizes, EXIF capture date and SHA-256 in `manifest.json`.
- **Formats** — JPEG, PNG and WebP output with adjustable quality; EXIF
  orientation is applied before resizing.
- **Self-contained demo** — generates 20 deterministic sample images plus one
  deliberately corrupt file in a temporary directory, runs the pipeline and
  verifies every output.

## Requirements

Python 3.10+ and Pillow:

```bash
python3 -m pip install -r requirements.txt
```

## Usage

```bash
python3 solution.py --demo
python3 solution.py photos -o thumbnails
python3 solution.py photos -o thumbnails --size 300x300 --workers 8
python3 solution.py photos --format webp --quality 80 --name-template "{index:04d}_{stem}"
python3 solution.py photos --report build/thumb-report.json --no-recursive
```

| Option | Meaning |
| --- | --- |
| `input` | Directory of source images (prompted for when omitted). |
| `-o, --output DIR` | Output directory (default `./thumbnails`). |
| `--size WxH` | Maximum bounding box, aspect ratio preserved (default `200x200`). |
| `--workers N` | Resize worker threads, 1–32 (default: up to 8). |
| `--format {jpeg,png,webp}` | Thumbnail encoding (default `jpeg`). |
| `--quality N` | JPEG/WebP quality, 1–100 (default 85; ignored for PNG). |
| `--name-template T` | Pattern using `{index}`, `{stem}`, `{date}`, `{width}`, `{height}`. |
| `--report PATH` | Manifest location (default `OUTPUT/manifest.json`). |
| `--no-recursive` | Scan only the top level of `input`. |
| `--strict` | Exit 1 if any individual image failed. |
| `-q, --quiet` | Suppress startup and live-status chatter (report still prints). |
| `--demo` | Generate sample images and run the scripted demonstration. |

Images are never upscaled: a source smaller than the bounding box keeps its
original dimensions. Thumbnails are written atomically from a `.staging`
directory inside the output folder, which is removed when the run finishes.

## Example Output

Trimmed `--demo` output (temporary paths shortened to `<tmp>`):

```
Bulk thumbnail demo
Generated 21 files in photos/ (20 valid images + 1 deliberately corrupt)
Input size: 364.75 KiB
Main thread: free while 4 resize workers and 1 renamer run.

  busy: resized 20/21, renamed 20, failed 0

Bulk thumbnail report
  source images : 21
  output dir    : <tmp>/thumbs
  settings      : max 160x160, JPEG q82, 4 workers
  elapsed       : 0.10s (197.8 images/s)
  succeeded     : 20
  failed        : 1
    - IMG_9999_broken.jpg [resize] UnidentifiedImageError: cannot identify image file 'IMG_9999_broken.jpg'
  bytes         : 364.22 KiB in -> 49.58 KiB out
  manifest      : <tmp>/thumbs/manifest.json
    001_IMG_0001_160x90.jpg  <-  IMG_0001.jpg  (960x540 -> 160x90)  captured 2024:05:01
    002_IMG_0002_160x107.jpg  <-  IMG_0002.jpg  (800x533 -> 160x107)  captured 2024:05:02
    003_IMG_0003_160x120.jpg  <-  IMG_0003.jpg  (960x720 -> 160x120)  captured 2024:05:03

Verification
  [PASS] 20 thumbnails produced
  [PASS] one corrupt input isolated
  [PASS] all thumbnails open and fit
  [PASS] manifest matches results

Demo complete: 4/4 checks passed.
```

## Implementation Notes

- **Stage 1 — resize.** A `ThreadPoolExecutor` with `--workers` threads opens
  each image, calls `Image.load()` so truncated files fail immediately,
  applies `ImageOps.exif_transpose`, converts incompatible modes (for example
  RGBA → RGB for JPEG), resizes with Lanczos, and encodes into
  `OUTPUT/.staging/<ordinal>.<ext>`.
- **Stage 2 — rename + metadata.** One thread drains a bounded
  `queue.Queue`, formats the naming template, resolves collisions with a
  reserved-name set, atomically `os.replace`s the staged file into place, and
  computes size and SHA-256 for the manifest. A single writer means no naming
  races and no locking around the entries list.
- **Backpressure.** The producer acquires a `BoundedSemaphore(2 × workers)`
  before submitting each job and releases it when the result has been queued.
  Combined with a bounded hand-off queue, this caps both in-flight decodes and
  queued results regardless of directory size.
- **Ordering.** Discovery is sorted, so `{index}` and the manifest order are
  stable. The pool itself completes out of order; the renamer preserves the
  original ordinal in every entry.
- **Why threads.** Pillow releases the GIL inside its C decode/encode paths,
  so resize workers overlap real work; the pipeline is also I/O-heavy
  (file reads/writes), where threads help further. `ProcessPoolExecutor` would
  add pickling overhead without a meaningful win for this workload.
- **Limitations.** The manifest is written once at the end (crash mid-run
  leaves staged files behind); collision suffixes are assigned in stage-2
  arrival order; animated GIF/WebP files are treated as their first frame;
  image formats are limited to what Pillow builds on the host support.
