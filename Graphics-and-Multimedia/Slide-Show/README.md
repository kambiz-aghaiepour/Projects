# Slide Show

**Category:** Graphics-and-Multimedia · **Project:** Slide-Show

## Problem

> Make an application that shows various pictures in a slide show format.
> Optional: Try adding various effects like fade in/out, star wipe and window
> blinds transitions.

## Features

- Loads individual image files or every supported image in a directory
  (PNG, JPEG, BMP, GIF, TIFF, WebP), applying EXIF orientation first.
- Fits arbitrary aspect ratios onto a fixed canvas: matching images fill the
  frame, other ratios sit on a blurred, dimmed version of themselves.
- Writes an animated **GIF** with real transition frames: cross-fade, soft-edge
  wipe, staggered window blinds, star wipe, or a cycle through fade → wipe →
  blinds. The loop closes back to the first slide.
- Writes a **single self-contained HTML file**: every slide is embedded as a
  base64 JPEG, so it works offline and can be emailed as one file. Includes
  keyboard navigation, autoplay, pause, dot navigation, captions and a
  fade/wipe effect selector.
- Configurable canvas size, hold time, transition length and frame count.
- `--no-gif` / `--no-html` let you produce just one output.

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Fully scripted demo: draws four sample slides, writes a GIF and an HTML viewer
python3 solution.py --demo

# Build both outputs from a folder
python3 solution.py photos/ --outdir build

# Animated GIF only, with a specific transition
python3 solution.py photos/ --no-html --transition wipe --hold 3 --gif tour.gif

# HTML only, 1280x720 canvas
python3 solution.py photos/ --no-gif --width 1280 --height 720 --html tour.html
```

| Option | Meaning |
| --- | --- |
| `--transition` | `fade`, `wipe`, `blinds`, `star`, or `cycle` (default) |
| `--hold SECONDS` | How long each slide rests (default `2.0`) |
| `--transition-ms MS` | Duration of each transition (default `700`) |
| `--steps N` | Frames per transition (default `8`) |
| `--width` / `--height` | Canvas dimensions (default `800x600`) |
| `--colors N` | GIF palette size, 2–256 (default `128`) |
| `--outdir DIR` | Default output directory for unspecified paths |
| `--no-gif`, `--no-html` | Skip one output |

With no images and no `--demo`, the program prompts for a folder (only when
stdin is a terminal).

## Example Output

```text
Slide Show demo
  generated : 4 sample slides (640x480)
              01-northern-lights.png  18.5 KiB
              02-city-afterglow.png  22.4 KiB
              03-tidal-forest.png  20.5 KiB
              04-desert-noon.png  20.4 KiB
  GIF       : slideshow.gif  28 frames  590.8 KiB
  HTML      : slideshow.html  121.0 KiB (self-contained, 4 slides)
  transitions: fade, wipe, blinds (GIF cycles all three)
Demo complete: open the HTML file in a browser or the GIF in any image viewer.
```

## Implementation Notes

- **Fade** is `Image.blend` between consecutive slides. **Wipe** composites the
  incoming frame through an L-mode mask with a feathered vertical edge.
  **Blinds** reveals ten horizontal bands with a staggered start. **Star**
  grows a 16-point polygon mask from the centre.
- Frames are quantized with Pillow's median-cut quantizer and saved with
  `save_all`, per-frame durations, `loop=0`, `disposal=2` and `optimize=True`.
  Each transition contributes `--steps` frames; holds contribute one frame.
- The HTML viewer uses CSS keyframe animations (`fadeIn`, `wipeIn`) applied to
  the incoming slide, with a JavaScript timer for autoplay. Images are embedded
  as JPEG data URIs, so no server or asset folder is needed.
- Transition cost is linear in canvas pixels × frames; a 28-frame 640×480 demo
  completes in under a second. Large photo sets make the HTML file large
  because every slide is embedded.
- Limitations: GIF output is limited to 256 colours per frame and cannot carry
  audio; the HTML viewer intentionally supports fade and wipe only.
