# Image Gallery

## Problem

Create an image abstract class and then a class that inherits from it for each
image type. Put them in a program which displays them in a gallery style
format for viewing.

This is the **Classes / Image Gallery** project. The demo generates sample
images, builds thumbnails and writes a responsive HTML gallery you can open in
a browser.

Project location: `Classes/Image-Gallery/` (`README.md`, `solution.py` and
`requirements.txt`).

## Features

- Abstract `Image` base class handling existence checks, real-format
  validation, dimensions, file size and thumbnail generation.
- One concrete subclass per format: `JPEGImage`, `PNGImage`, `GIFImage`,
  `BMPImage`, `TIFFImage` and `WebPImage`. Each declares its extensions and
  checks the actual Pillow format, so a `.png` that really contains JPEG data
  is rejected rather than mislabelled.
- `Gallery` discovers images in a folder (optionally recursive), skips
  non-images and duplicates, and renders a responsive dark-mode HTML contact
  sheet with caption metadata.
- Thumbnails are proportional, use Lanczos resampling, are normalised to
  RGB/RGBA and saved as PNG; originals are linked from each card.
- Demo creates five deterministic sample images (gradient/PNG, checkerboard/
  JPEG, concentric rings/GIF, stripes/BMP, mosaic/WebP) in a temporary folder.
- Graceful errors for missing, unsupported and corrupt files.

## Requirements

Python 3.10+ and Pillow 10 or newer:

```bash
pip install -r requirements.txt
```

Pillow is the only third-party dependency and is used only for decoding,
thumbnail generation and drawing the demo images.

## Usage

```bash
pip install -r requirements.txt
python3 solution.py --demo
python3 solution.py ~/Pictures --output gallery --title "My Pictures"
python3 solution.py ~/Pictures --recursive --thumb-size 400 --columns 3
```

| Option | Meaning |
| --- | --- |
| `directory` | Folder to scan. If omitted (and no `--demo`), help is printed. |
| `--demo` | Generate sample images and a complete gallery in a temp folder. |
| `--output DIR` | Where `index.html` and `thumbnails/` are written (default `./gallery`). |
| `--title TEXT` | Gallery heading. |
| `--thumb-size PX` | Maximum thumbnail edge, minimum 16 (default 320). |
| `--columns N` | Number of grid columns on wide screens (responsive down to one). |
| `--recursive` | Include images in subfolders. |

Open `<output>/index.html` in any browser; no server is required.

## Example Output

```text
=== Image Gallery: demo ===

Generating sample images:
  created sunset.png          5.7 KiB
  created checkerboard.jpg   29.1 KiB
  created rings.gif           7.2 KiB
  created stripes.bmp        675.1 KiB
  created mosaic.webp        14.4 KiB

Discovered 5 images (notes.txt skipped).
File                 Class        Format   Size            Bytes
----------------------------------------------------------------
checkerboard.jpg     JPEGImage    JPEG     600x450         29836
mosaic.webp          WebPImage    WEBP     512x512         14718
rings.gif            GIFImage     GIF      480x480          7404
stripes.bmp          BMPImage     BMP      640x360        691254
sunset.png           PNGImage     PNG      640x400          5819

Gallery: 5 thumbnails, HTML 3726 bytes
Location: <temporary folder>/gallery
Title: Classes / Image Gallery; originals total 731.5 KiB

Thumbnail check:
  checkerboard.jpg: 600x450 -> 160x120

Validation checks:
  unsupported file: rejected -> unsupported image type '.txt'; supported: .jpg, .jpeg, .png, .gif, .bmp, .tif, .tiff, .webp
  missing file: rejected -> image not found: .../samples/missing.png

Demo complete; open the gallery above in a browser.
```

The generated `index.html` contains one card per image:

```html
<figure class="card">
  <a href="file:///.../sunset.png" target="_blank">
    <img src="thumbnails/00-sunset.png" alt="sunset" loading="lazy" width="240" height="150">
  </a>
  <figcaption><strong>sunset.png</strong>
    <span>PNG &middot; 640 &times; 400 &middot; 5.7 KiB</span>
  </figcaption>
</figure>
```

## Implementation Notes

- `Image` is a genuine `abc.ABC` with an abstract classmethod `supports()`.
  Subclasses answer "does this extension belong to me?" and the base class
  verifies `PIL.Image.format` on open, so extension spoofing is caught.
- `image_for_path()` walks the registry of subclasses and returns an instance
  of the matching concrete type; unsupported suffixes produce a message with
  the complete supported list.
- `thumbnail()` copies the decoded frame before calling Pillow's
  `thumbnail()`, because that method mutates in place. Palette and CMYK images
  are converted to RGBA/RGB so PNG output is always safe.
- `validate()` re-opens and calls `PIL.Image.verify()`; the demo validates all
  five samples before rendering.
- Rendering escapes every filename/title with `html.escape`, writes
  `index.html` plus `thumbnails/NN-slug.png`, and records a plain-text
  manifest (`gallery.txt`). Thumbnail names are slugified and index-prefixed to
  avoid collisions between folders.
- GIF support shows the first frame only. EXIF orientation is not applied, and
  SVG is not supported (it is not a raster format). Very large folders are
  processed sequentially; memory use stays low because each source image is
  opened only for the duration of its thumbnail.
