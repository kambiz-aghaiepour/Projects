# Watermarking Application

**Category:** Graphics-and-Multimedia · **Project:** Watermarking-Application

## Problem

> Add your own logo or text lightly across the background of pictures so that
> no one can simply steal your graphics. Optional: Use threading to process
> multiple images simultaneously.

## Features

- **Text watermarks** with a custom string, font size, colour, drop shadow,
  rotation and opacity.
- **Logo watermarks** from any Pillow-readable image (PNG transparency is
  honoured), scaled relative to the photo, faded and optionally rotated.
- **Nine anchors** for both text and logo (`top-left` … `bottom-right`, plus
  `center`), and a **tiled** mode that repeats the text in a staggered grid
  across the whole picture.
- **Batch processing** with a `ThreadPoolExecutor` (`--workers`), preserving
  input order in the report.
- **EXIF orientation is applied before drawing** (`ImageOps.exif_transpose`)
  and the saved copy gets `Orientation = 1`, so viewers never rotate the
  watermarked file a second time.
- Keeps JPEG quality/progressive encoding, supports PNG/WebP/TIFF output, and
  never overwrites an existing result (adds `_1`, `_2`, …).
- Per-file timing and error reporting; one bad image does not stop the batch.

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scripted demo: creates four photos (one with EXIF orientation 6), a logo,
# then watermarks them with four worker threads
python3 solution.py --demo

# Text watermark over every image in a folder
python3 solution.py photos/ --text "(c) Studio 2026" --position bottom-right

# Text plus logo, tiled text at low opacity, 8 threads
python3 solution.py photos/ --text "SAMPLE" --tile --opacity 0.16 \
    --logo logo.png --logo-position bottom-left --workers 8 --outdir out

# Rotated text in the centre, 20% opacity
python3 solution.py cover.jpg --text "DRAFT" --angle -30 --opacity 0.2 \
    --position center --font-size 90
```

| Option | Meaning |
| --- | --- |
| `--text` / `--logo` | Watermark content; at least one is required |
| `--position` | Text anchor: nine compass positions (default `bottom-right`) |
| `--logo-position` | Logo anchor (default `top-left`) |
| `--opacity` | 0.0–1.0 alpha multiplier (default `0.25`) |
| `--scale` | Logo width as a fraction of photo width (default `0.18`) |
| `--angle` | Rotation in degrees for both layers (default `0`) |
| `--font-size` | Text size in pixels (default `34`) |
| `--tile` | Repeat the text across the image |
| `--margin` | Edge margin in pixels (default `24`) |
| `--workers` | Thread pool size (default `4`) |
| `--quality` | JPEG/WebP quality 1–100 (default `92`) |
| `--outdir` | Output folder (default `watermarked`) |

## Example Output

```text
Watermarking Application demo
  generated: 4 photos + logo.png
  batch    : 4 images with 4 worker threads in 18 ms
    [OK ] coastline.jpg                900x600 -> 58 KiB
    [OK ] pine-ridge.jpg               900x600 -> 56 KiB
    [OK ] harbor.jpg                   900x600 -> 59 KiB
    [OK ] portrait-orientation.jpg     500x800 -> 46 KiB
  tiled    : OK coastline_watermarked.jpg
  EXIF     : stored 800x500 with orientation=6 -> saved upright 500x800, tag=1
  checks   : 5/5 passed
Demo complete: inspect the watermarked JPEGs in the workspace.
```

## Implementation Notes

- Both watermarks are rendered onto transparent RGBA layers. Opacity is applied
  by multiplying the layer's alpha channel, which keeps text edges smooth and
  lets the photograph show through uniformly.
- Text is measured with `textbbox` (including stroke width) so the shadow and
  glyphs are not clipped; rotation uses bicubic resampling with `expand=True`.
- The logo is scaled to `--scale × image width`, capped so it never exceeds 40%
  of the image height. It is composited with `Image.alpha_composite`.
- `open_upright()` calls `exif_transpose()` and then rewrites EXIF tag `0x0112`
  to `1` before saving. This is what prevents the common “watermark is sideways
  after upload” bug.
- Threading helps because decoding, resampling and JPEG encoding release the
  GIL inside Pillow; four images finish in roughly the time of the slowest one.
  Results are collected with `executor.map`, so the printed order matches the
  input order even though work completes out of order.
- Limitations: text tiling only (logos are placed once), no PDF/video support,
  and no automatic face-aware placement. Very large batches are bounded by
  memory because each worker holds one decoded image at a time.
