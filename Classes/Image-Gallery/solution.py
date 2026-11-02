#!/usr/bin/env python3
"""Image Gallery.

An abstract ``Image`` class models one image file; concrete subclasses
(JPEG, PNG, GIF, BMP, TIFF, WebP) validate the real format through Pillow.
A ``Gallery`` discovers images, builds thumbnails and renders a responsive
HTML contact sheet you can open in any browser.

Run ``python3 solution.py --demo`` to generate sample images and a gallery.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Optional

try:  # Pillow is an optional import so --help works without it.
    from PIL import Image as PILImage
    from PIL import ImageDraw
    from PIL import UnidentifiedImageError
except ImportError:  # pragma: no cover - exercised only without Pillow
    PILImage = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[assignment,misc]

THUMBNAIL_DIR = "thumbnails"


class ImageError(Exception):
    """Base error for unsupported, missing or corrupt images."""


class UnsupportedImageError(ImageError):
    """Raised when no image subclass handles a file."""


class Image(ABC):
    """Abstract base class for a single image file.

    Subclasses declare the Pillow format they represent and which filename
    extensions belong to them.  All loading, measuring and thumbnail work is
    shared here; subclasses only answer the format-specific questions.
    """

    format_name: ClassVar[str] = ""
    extensions: ClassVar[tuple[str, ...]] = ()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ImageError(f"image not found: {self.path}")

    # -- subclass contract ---------------------------------------------
    @classmethod
    @abstractmethod
    def supports(cls, path: Path) -> bool:
        """Return True when this subclass can handle *path*."""

    # -- shared behaviour ----------------------------------------------
    def _open(self) -> Any:
        if PILImage is None:
            raise ImageError("Pillow is required; install it with 'pip install -r requirements.txt'")
        try:
            image = PILImage.open(self.path)
        except (OSError, UnidentifiedImageError) as exc:
            raise ImageError(f"cannot read {self.path.name}: {exc}") from exc
        if image.format != self.format_name:
            image.close()
            raise ImageError(
                f"{self.path.name} contains {image.format or 'unknown'} data, "
                f"not {self.format_name}"
            )
        return image

    def validate(self) -> None:
        """Fully decode the file so corrupt images fail early."""
        try:
            with self._open() as image:
                image.verify()
        except ImageError:
            raise
        except Exception as exc:  # Pillow raises a variety of low-level errors
            raise ImageError(f"corrupt image {self.path.name}: {exc}") from exc

    @property
    def width(self) -> int:
        with self._open() as image:
            return image.width

    @property
    def height(self) -> int:
        with self._open() as image:
            return image.height

    @property
    def size(self) -> tuple[int, int]:
        with self._open() as image:
            return image.size

    @property
    def mode(self) -> str:
        with self._open() as image:
            return image.mode

    @property
    def file_size(self) -> int:
        return self.path.stat().st_size

    def aspect_ratio(self) -> float:
        width, height = self.size
        return width / height if height else 0.0

    def thumbnail(self, max_size: int = 320) -> Any:
        """Return a proportional RGB/RGBA thumbnail no larger than *max_size*."""
        if max_size < 16:
            raise ImageError("thumbnail size must be at least 16 pixels")
        if PILImage is None:
            raise ImageError("Pillow is required; install it with 'pip install -r requirements.txt'")
        with self._open() as source:
            thumb = source.copy()
        thumb.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
        if thumb.mode not in {"RGB", "RGBA"}:
            thumb = thumb.convert("RGBA")
        return thumb

    def info(self) -> dict[str, object]:
        """Return metadata suitable for the gallery caption."""
        return {
            "name": self.path.name,
            "class": type(self).__name__,
            "format": self.format_name,
            "width": self.width,
            "height": self.height,
            "mode": self.mode,
            "bytes": self.file_size,
        }

    def __str__(self) -> str:
        width, height = self.size
        return f"{self.path.name} ({self.format_name}, {width}x{height})"


class JPEGImage(Image):
    format_name = "JPEG"
    extensions = (".jpg", ".jpeg")

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


class PNGImage(Image):
    format_name = "PNG"
    extensions = (".png",)

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


class GIFImage(Image):
    format_name = "GIF"
    extensions = (".gif",)

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


class BMPImage(Image):
    format_name = "BMP"
    extensions = (".bmp",)

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


class TIFFImage(Image):
    format_name = "TIFF"
    extensions = (".tif", ".tiff")

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


class WebPImage(Image):
    format_name = "WEBP"
    extensions = (".webp",)

    @classmethod
    def supports(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions


IMAGE_TYPES: tuple[type[Image], ...] = (
    JPEGImage, PNGImage, GIFImage, BMPImage, TIFFImage, WebPImage,
)


def image_for_path(path: str | Path) -> Image:
    """Instantiate the right Image subclass for *path*."""
    candidate = Path(path)
    if not candidate.is_file():
        raise ImageError(f"image not found: {candidate}")
    for image_type in IMAGE_TYPES:
        if image_type.supports(candidate):
            return image_type(candidate)
    supported = ", ".join(ext for cls in IMAGE_TYPES for ext in cls.extensions)
    raise UnsupportedImageError(
        f"unsupported image type {candidate.suffix or '(none)'!r}; supported: {supported}"
    )


def human_bytes(count: int) -> str:
    """Format a byte count in binary units."""
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


class Gallery:
    """An ordered collection of images that renders itself as HTML."""

    def __init__(self, title: str = "Image Gallery") -> None:
        self.title = title.strip() or "Image Gallery"
        self.images: list[Image] = []

    def __len__(self) -> int:
        return len(self.images)

    def add(self, image: Image) -> None:
        if any(existing.path == image.path for existing in self.images):
            raise ImageError(f"{image.path.name} is already in the gallery")
        self.images.append(image)

    def add_path(self, path: str | Path) -> Image:
        image = image_for_path(path)
        self.add(image)
        return image

    def discover(self, directory: str | Path, recursive: bool = False) -> list[Image]:
        """Add every supported image below *directory*, sorted by path."""
        root = Path(directory)
        if not root.is_dir():
            raise ImageError(f"not a directory: {root}")
        pattern = "**/*" if recursive else "*"
        added: list[Image] = []
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                added.append(self.add_path(path))
            except UnsupportedImageError:
                continue
        return added

    @property
    def total_bytes(self) -> int:
        return sum(image.file_size for image in self.images)

    def render(self, output_dir: str | Path, thumb_size: int = 320,
               columns: int = 4) -> Path:
        """Write thumbnails and ``index.html``; return the HTML path."""
        if not self.images:
            raise ImageError("cannot render an empty gallery")
        destination = Path(output_dir)
        thumbs = destination / THUMBNAIL_DIR
        thumbs.mkdir(parents=True, exist_ok=True)

        cards: list[str] = []
        for index, image in enumerate(self.images):
            thumb = image.thumbnail(thumb_size)
            thumb_name = f"{index:02d}-{_slug(image.path.stem)}.png"
            thumb.save(thumbs / thumb_name, format="PNG")
            width, height = image.size
            cards.append(
                f'<figure class="card">'
                f'<a href="{html.escape(image.path.resolve().as_uri())}" target="_blank">'
                f'<img src="{THUMBNAIL_DIR}/{thumb_name}" alt="{html.escape(image.path.stem)}" '
                f'loading="lazy" width="{thumb.width}" height="{thumb.height}"></a>'
                f'<figcaption><strong>{html.escape(image.path.name)}</strong>'
                f'<span>{image.format_name} &middot; {width} &times; {height} '
                f'&middot; {human_bytes(image.file_size)}</span></figcaption>'
                f'</figure>'
            )

        page = _HTML_TEMPLATE.format(
            title=html.escape(self.title),
            count=len(self.images),
            total=human_bytes(self.total_bytes),
            columns=max(1, columns),
            cards="\n".join(cards),
        )
        index_path = destination / "index.html"
        index_path.write_text(page, encoding="utf-8")

        manifest = destination / "gallery.txt"
        manifest.write_text(
            "\n".join(str(image) for image in self.images) + "\n", encoding="utf-8"
        )
        return index_path


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "image"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #101318;
    --panel: #191e26;
    --ink: #e8edf4;
    --muted: #96a1b1;
    --accent: #f3b64b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem clamp(1rem, 4vw, 4rem);
    background: radial-gradient(circle at top left, #1b2230, var(--bg) 55%);
    color: var(--ink);
    font: 16px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif;
  }}
  header {{ margin-bottom: 2rem; border-bottom: 1px solid #2a3342; padding-bottom: 1rem; }}
  h1 {{ margin: 0 0 .35rem; font-size: clamp(1.6rem, 3vw, 2.4rem); letter-spacing: -.02em; }}
  header p {{ margin: 0; color: var(--muted); }}
  .grid {{
    display: grid; gap: 1.2rem;
    grid-template-columns: repeat({columns}, minmax(0, 1fr));
  }}
  @media (max-width: 900px) {{
    .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
  @media (max-width: 560px) {{
    .grid {{ grid-template-columns: 1fr; }}
  }}
  .card {{
    margin: 0; background: var(--panel); border: 1px solid #273040;
    border-radius: 14px; overflow: hidden; transition: transform .18s ease, border-color .18s ease;
  }}
  .card:hover {{ transform: translateY(-3px); border-color: var(--accent); }}
  .card a {{ display: block; background: #0c0f14; aspect-ratio: 4 / 3; }}
  .card img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  figcaption {{ padding: .75rem .9rem .9rem; display: grid; gap: .2rem; }}
  figcaption strong {{ font-size: .95rem; overflow-wrap: anywhere; }}
  figcaption span {{ color: var(--muted); font-size: .78rem; }}
  footer {{ margin-top: 2.5rem; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p>{count} images &middot; {total}</p>
</header>
<main class="grid">
{cards}
</main>
<footer>Built with the Image Gallery abstract-class demo.</footer>
</body>
</html>
"""


def _gradient(width: int, height: int, top: tuple[int, int, int],
              bottom: tuple[int, int, int]) -> Any:
    """Create a vertical RGB gradient."""
    assert PILImage is not None
    image = PILImage.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(top[c] + (bottom[c] - top[c]) * ratio) for c in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def create_sample_images(directory: Path) -> list[Path]:
    """Draw five deterministic sample images in different formats."""
    assert PILImage is not None and ImageDraw is not None
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    sunset = _gradient(640, 400, (252, 176, 69), (76, 40, 110))
    draw = ImageDraw.Draw(sunset)
    draw.ellipse((430, 90, 590, 250), fill=(255, 230, 160))
    draw.polygon([(0, 330), (180, 210), (330, 330)], fill=(58, 34, 74))
    draw.polygon([(220, 350), (430, 190), (640, 350)], fill=(41, 24, 58))
    draw.rectangle((0, 350, 640, 400), fill=(23, 14, 33))
    sunset_path = directory / "sunset.png"
    sunset.save(sunset_path, "PNG")
    paths.append(sunset_path)

    checker = PILImage.new("RGB", (600, 450), (245, 239, 226))
    draw = ImageDraw.Draw(checker)
    tile = 75
    for row in range(6):
        for column in range(8):
            if (row + column) % 2 == 0:
                draw.rectangle((column * tile, row * tile,
                                (column + 1) * tile - 1, (row + 1) * tile - 1),
                               fill=(38, 84, 124))
    draw.rectangle((0, 0, 599, 449), outline=(214, 162, 74), width=10)
    checker_path = directory / "checkerboard.jpg"
    checker.save(checker_path, "JPEG", quality=90)
    paths.append(checker_path)

    rings = PILImage.new("P", (480, 480), color=0)
    draw = ImageDraw.Draw(rings)
    palette = [0, 0, 0, 255, 214, 109, 255, 170, 64, 92, 60, 130,
               44, 129, 156, 236, 238, 222, 210, 72, 96]
    rings.putpalette(palette)
    for step in range(8, 0, -1):
        radius = step * 28
        draw.ellipse((240 - radius, 240 - radius, 240 + radius, 240 + radius),
                     fill=(step % 5) + 1)
    rings_path = directory / "rings.gif"
    rings.save(rings_path, "GIF")
    paths.append(rings_path)

    stripes = PILImage.new("RGB", (640, 360), (16, 32, 48))
    draw = ImageDraw.Draw(stripes)
    for offset in range(-360, 760, 48):
        draw.polygon([(offset, 360), (offset + 180, 360), (offset + 400, 0), (offset + 220, 0)],
                     fill=(33, 150, 143))
    draw.line((0, 300, 640, 300), fill=(244, 196, 48), width=8)
    stripes_path = directory / "stripes.bmp"
    stripes.save(stripes_path, "BMP")
    paths.append(stripes_path)

    mosaic = PILImage.new("RGB", (512, 512), (18, 18, 24))
    draw = ImageDraw.Draw(mosaic)
    colors = [(232, 93, 117), (244, 162, 97), (42, 157, 143),
              (38, 70, 83), (144, 190, 109), (249, 199, 79)]
    cell = 64
    for row in range(8):
        for column in range(8):
            color = colors[(row * 3 + column * 5) % len(colors)]
            inset = (row + column) % 3 * 5
            draw.rounded_rectangle(
                (column * cell + inset, row * cell + inset,
                 (column + 1) * cell - inset - 4, (row + 1) * cell - inset - 4),
                radius=8, fill=color)
    mosaic_path = directory / "mosaic.webp"
    mosaic.save(mosaic_path, "WEBP", quality=88)
    paths.append(mosaic_path)

    return paths


def run_demo() -> int:
    """Create sample images, build a gallery and report what happened."""
    if PILImage is None:
        print("Pillow is not installed; run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    print("=== Image Gallery: demo ===\n")
    root = Path(tempfile.mkdtemp(prefix="image-gallery-demo-"))
    source = root / "samples"
    print("Generating sample images:")
    for path in create_sample_images(source):
        print(f"  created {path.name:<18} {human_bytes(path.stat().st_size):>8}")
    (source / "notes.txt").write_text("not an image\n", encoding="utf-8")

    gallery = Gallery("Classes / Image Gallery")
    found = gallery.discover(source)
    print(f"\nDiscovered {len(found)} images (notes.txt skipped).")
    print(f"{'File':<20} {'Class':<12} {'Format':<8} {'Size':<12} {'Bytes':>8}")
    print("-" * 64)
    for image in gallery.images:
        width, height = image.size
        print(f"{image.path.name:<20} {type(image).__name__:<12} {image.format_name:<8} "
              f"{f'{width}x{height}':<12} {image.file_size:>8}")
        image.validate()

    output = root / "gallery"
    index = gallery.render(output, thumb_size=240, columns=4)
    thumbs = sorted((output / THUMBNAIL_DIR).glob("*.png"))
    print(f"\nGallery: {len(thumbs)} thumbnails, HTML {index.stat().st_size} bytes")
    print(f"Location: {index.parent}")
    print(f"Title: {gallery.title}; originals total {human_bytes(gallery.total_bytes)}")

    print("\nThumbnail check:")
    sample = gallery.images[0]
    thumb = sample.thumbnail(160)
    print(f"  {sample.path.name}: {sample.width}x{sample.height} -> "
          f"{thumb.width}x{thumb.height}")

    print("\nValidation checks:")
    try:
        gallery.add_path(source / "notes.txt")
    except UnsupportedImageError as exc:
        print(f"  unsupported file: rejected -> {exc}")
    try:
        gallery.add_path(source / "missing.png")
    except ImageError as exc:
        print(f"  missing file: rejected -> {exc}")

    print("\nDemo complete; open the gallery above in a browser.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an HTML thumbnail gallery from a folder of images.",
        epilog="Supports JPEG, PNG, GIF, BMP, TIFF and WebP via Pillow.",
    )
    parser.add_argument("directory", nargs="?", type=Path,
                        help="folder containing images to display")
    parser.add_argument("--demo", action="store_true",
                        help="generate sample images and a gallery in a temp folder")
    parser.add_argument("--output", type=Path, default=Path("gallery"),
                        help="output folder (default: ./gallery)")
    parser.add_argument("--title", default="Image Gallery", help="gallery heading")
    parser.add_argument("--thumb-size", type=int, default=320, metavar="PX",
                        help="maximum thumbnail edge in pixels (default: 320)")
    parser.add_argument("--columns", type=int, default=4,
                        help="preferred grid columns (default: 4)")
    parser.add_argument("--recursive", action="store_true",
                        help="scan subfolders too")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if args.directory is None:
        parser.print_help()
        return 0

    try:
        gallery = Gallery(args.title)
        gallery.discover(args.directory, recursive=args.recursive)
        index = gallery.render(args.output, thumb_size=args.thumb_size, columns=args.columns)
    except ImageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered {len(gallery)} images to {index}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
