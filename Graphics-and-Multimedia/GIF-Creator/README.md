# GIF Creator

**Category:** Graphics-and-Multimedia · **Project:** GIF-Creator

## Problem

> A program that puts together multiple images (PNGs, JPGs, TIFFs) to make a
> smooth GIF that can be exported. Optional: convert small video files to GIFs
> as well.

## Features

- Combine PNG/JPEG/BMP/TIFF/WebP images, or every image in a folder, in sorted
  order.
- Fit frames with `contain` (letterbox), `cover` (crop) or `stretch`, all
  resized with Lanczos filtering.
- Control **frame duration**, **loop count**, **palette size** (2–256),
  **canvas size** and **GIF optimisation**.
- **Shared global palette** built from a contact sheet of all frames, which
  prevents the colour flicker you get from per-frame palettes; `--per-frame-palette`
  switches back if you prefer.
- **Video → GIF** through `ffmpeg`: sample at a chosen FPS, start offset,
  maximum duration and width. Frames are extracted to a temporary directory and
  fed through the same canvas/palette pipeline.
- Reports exactly what was written (frame count, dimensions, byte size, loop)
  and verifies the encoded GIF in the demo.

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

`ffmpeg` is optional, needed only for `--video`.

## Usage

```bash
# Scripted demo: 24 synthesised frames plus a video-to-GIF round trip
python3 solution.py --demo

# All images in a folder, 80 ms per frame, 128 colours, forever loop
python3 solution.py frames/ --out spin.gif --duration 80 --colors 128

# Fit a 16:9 canvas by cropping, loop three times
python3 solution.py shots/ --width 640 --height 360 --fit cover --loop 3

# Convert the first 5 seconds of a video at 12 fps
python3 solution.py --video clip.mp4 --fps 12 --max-seconds 5 --width 480 --out clip.gif

# One-shot GIF from a single image (hold frame), 1 second
python3 solution.py still.png --duration 1000 --out still.gif
```

| Option | Meaning |
| --- | --- |
| `IMAGE_OR_DIR...` | Image files or folders to combine (sorted) |
| `--video FILE` | Extract frames from a video instead of images |
| `--out PATH` | Output GIF (default `animation.gif`) |
| `--duration MS` | Milliseconds per frame (default `100`) |
| `--loop N` | `0` = forever, `N` = extra repeats (default `0`) |
| `--colors N` | Palette size 2–256 (default `128`) |
| `--width` / `--height` | Canvas size (default `480x360`) |
| `--fit` | `contain`, `cover` or `stretch` (default `contain`) |
| `--per-frame-palette` | Use a palette per frame instead of a shared one |
| `--no-optimize` | Disable GIF frame optimisation |
| `--fps`, `--start`, `--max-seconds` | Video sampling controls (default `12`, `0`, `6`) |

## Example Output

```text
GIF Creator demo
  images   : 24 synthesised frames -> bouncing-ball.gif
             24 frames, 480x360, 326.0 KiB, 80 ms/frame, loop forever
  verified : n_frames=24, size=480x360, duration=80 ms
  video    : 24 frames, 360x270, 381.7 KiB from sample.mp4
  checks   : 6/6 passed
Demo complete: open bouncing-ball.gif in any viewer.
```

## Implementation Notes

- Frames are normalised to RGB and resized once with Lanczos. `contain` pastes
  the thumbnail onto a dark canvas; `cover` uses `ImageOps.fit` for a
  centre-weighted crop.
- A shared palette is produced by tiling small thumbnails of every frame into a
  contact sheet, quantizing that sheet with median cut, then mapping each frame
  through it (`Image.quantize(palette=...)`). This is much more stable than
  quantizing each frame independently. Floyd–Steinberg dithering smooths
  gradients at the cost of some file size.
- GIFs are written with `save_all=True`, a duration for every frame,
  `disposal=2`, `optimize=True`, and the requested loop count. Pillow stores
  durations in centiseconds internally, so sub-20 ms values are clamped.
- Video frames come from `ffmpeg -ss … -t … -vf fps=…,scale=…` into a
  `TemporaryDirectory`; the frames are then treated exactly like image inputs,
  so all fitting/palette options apply.
- Limitations: GIF is limited to 256 colours and has no audio; very long videos
  are loaded as individual Pillow frames, so memory grows with frame count.
  `--video` requires ffmpeg to be installed and on `PATH`.
