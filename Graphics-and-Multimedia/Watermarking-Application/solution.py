#!/usr/bin/env python3
"""Batch image watermarking with text and logo overlays.

Watermarks can be positioned at any of nine anchors or tiled across the image,
with configurable opacity, scale and rotation.  Images are processed in a
thread pool, EXIF orientation is applied before drawing, and the saved file
carries a normalised orientation tag so viewers do not rotate it twice.

Usage::

    python3 solution.py photos/ --text "(c) Studio 2026" --logo logo.png
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
POSITIONS = (
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
)
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
)


def require_pillow() -> None:
    if Image is None:
        raise SystemExit("Pillow is required: pip install -r requirements.txt")


def load_font(size: int) -> "ImageFont.ImageFont":
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


@dataclass
class WatermarkOptions:
    """Everything that controls how a watermark is rendered."""

    text: str | None = None
    logo: Path | None = None
    opacity: float = 0.25
    position: str = "bottom-right"
    logo_position: str = "top-left"
    scale: float = 0.18
    angle: float = 0.0
    tile: bool = False
    margin: int = 24
    font_size: int = 34
    color: tuple[int, int, int] = (255, 255, 255)
    shadow: bool = True


@dataclass
class Result:
    """Outcome of processing one file."""

    source: Path
    output: Path | None
    seconds: float
    detail: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.output is not None


def open_upright(path: Path) -> tuple["Image.Image", bytes | None]:
    """Open an image, apply its EXIF orientation and normalise the tag."""
    image = Image.open(path)
    image.load()
    exif = image.getexif()
    upright = ImageOps.exif_transpose(image)
    exif_bytes = None
    if exif:
        exif[0x0112] = 1  # orientation: normal
        try:
            exif_bytes = exif.tobytes()
        except (ValueError, OSError):
            exif_bytes = None
    upright.load()
    return upright, exif_bytes


def _text_layer(options: WatermarkOptions, image_size: tuple[int, int]) -> "Image.Image" | None:
    """Render the text on a transparent layer, rotated and faded."""
    if not options.text:
        return None
    font = load_font(max(8, options.font_size))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), options.text, font=font, stroke_width=1)
    width, height = right - left + 8, bottom - top + 8
    layer = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    origin = (4 - left, 4 - top)
    if options.shadow:
        draw.text((origin[0] + 2, origin[1] + 2), options.text, font=font, fill=(0, 0, 0, 255), stroke_width=1)
    draw.text(origin, options.text, font=font, fill=(*options.color, 255), stroke_width=1, stroke_fill=(0, 0, 0, 90))
    if options.angle:
        layer = layer.rotate(options.angle, expand=True, resample=Image.Resampling.BICUBIC)
    alpha = layer.getchannel("A").point(lambda value: int(value * options.opacity))
    layer.putalpha(alpha)
    return layer


def _logo_layer(options: WatermarkOptions, image_size: tuple[int, int]) -> "Image.Image" | None:
    """Load and scale the logo onto a transparent, faded layer."""
    if not options.logo:
        return None
    with Image.open(options.logo) as opened:
        logo = ImageOps.exif_transpose(opened).convert("RGBA")
    target_width = max(16, int(image_size[0] * options.scale))
    target_width = min(target_width, max(16, int(image_size[0] * 0.8)))
    ratio = target_width / logo.width
    target_height = max(8, int(logo.height * ratio))
    if target_height > image_size[1] * 0.4:
        target_height = int(image_size[1] * 0.4)
        target_width = max(8, int(logo.width * target_height / logo.height))
    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
    if options.angle:
        logo = logo.rotate(options.angle, expand=True, resample=Image.Resampling.BICUBIC)
    alpha = logo.getchannel("A").point(lambda value: int(value * options.opacity))
    logo.putalpha(alpha)
    return logo


def _anchor(image_size: tuple[int, int], layer_size: tuple[int, int], position: str, margin: int) -> tuple[int, int]:
    """Compute the pasted position of a layer for a named anchor."""
    width, height = image_size
    layer_w, layer_h = layer_size
    vertical, _, horizontal = position.partition("-")
    if position == "center":
        horizontal, vertical = "center", "center"
    x = {
        "left": margin,
        "center": (width - layer_w) // 2,
        "right": width - layer_w - margin,
    }.get(horizontal, margin)
    y = {
        "top": margin,
        "center": (height - layer_h) // 2,
        "bottom": height - layer_h - margin,
    }.get(vertical, margin)
    return x, y


def _tile_positions(canvas: tuple[int, int], layer: tuple[int, int], gap: int) -> Iterable[tuple[int, int]]:
    """Yield positions on a staggered grid covering the whole canvas."""
    step_x = layer[0] + gap
    step_y = layer[1] + max(16, gap // 2)
    row = 0
    y = -layer[1] // 2
    while y < canvas[1]:
        offset = -(step_x // 2) if row % 2 else 0
        x = offset
        while x < canvas[0]:
            yield x, y
            x += step_x
        y += step_y
        row += 1


def add_watermarks(image: "Image.Image", options: WatermarkOptions) -> "Image.Image":
    """Return a copy of ``image`` with text and/or logo watermarks applied."""
    base = image.convert("RGBA")
    text_layer = _text_layer(options, base.size)
    logo_layer = _logo_layer(options, base.size)

    for layer, position, tiled in (
        (text_layer, options.position, options.tile),
        (logo_layer, options.logo_position, False),
    ):
        if layer is None:
            continue
        if tiled:
            gap = max(layer.size[1] // 2, 24)
            for x, y in _tile_positions(base.size, layer.size, gap):
                base.alpha_composite(layer, (max(0, x), max(0, y)))
        else:
            base.alpha_composite(layer, _anchor(base.size, layer.size, position, options.margin))
    return base


def _save(image: "Image.Image", destination: Path, quality: int, exif: bytes | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        save_args = {"quality": quality, "optimize": True, "progressive": True}
        if exif:
            save_args["exif"] = exif
        image.convert("RGB").save(destination, **save_args)
    elif suffix == ".webp":
        image.save(destination, quality=quality, method=6)
    else:
        image.save(destination, optimize=True)


def process_file(source: Path, outdir: Path, options: WatermarkOptions, quality: int = 92) -> Result:
    """Watermark one file, returning a structured result (never raises)."""
    started = time.perf_counter()
    try:
        image, exif = open_upright(source)
        original_size = image.size
        marked = add_watermarks(image, options)
        destination = outdir / f"{source.stem}_watermarked{source.suffix.lower()}"
        counter = 1
        while destination.exists() and destination != source:
            destination = outdir / f"{source.stem}_watermarked_{counter}{source.suffix.lower()}"
            counter += 1
        _save(marked, destination, quality, exif)
        detail = f"{original_size[0]}x{original_size[1]} -> {destination.stat().st_size / 1024:.0f} KiB"
        return Result(source, destination, time.perf_counter() - started, detail)
    except (OSError, ValueError) as exc:
        return Result(source, None, time.perf_counter() - started, "", str(exc))


def collect_inputs(paths: Sequence[str]) -> list[Path]:
    """Expand files and directories into a sorted list of images."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            found.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED))
        elif path.is_file() and path.suffix.lower() in SUPPORTED:
            found.append(path)
        elif path.is_file():
            raise ValueError(f"unsupported image type: {path}")
        else:
            raise FileNotFoundError(f"no such file or directory: {path}")
    if not found:
        raise ValueError("no supported images found")
    return found


def run_batch(inputs: Sequence[Path], outdir: Path, options: WatermarkOptions, workers: int, quality: int = 92) -> list[Result]:
    """Process every input concurrently, preserving input order in the results."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda path: process_file(path, outdir, options, quality), inputs))


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> "Image.Image":
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        t = y / max(1, height - 1)
        pixels[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize(size, Image.Resampling.BILINEAR)


def make_demo_photos(directory: Path) -> list[Path]:
    """Create four synthetic photos, one with a non-trivial EXIF orientation."""
    specs = [
        ("coastline", (900, 600), (12, 40, 60), (240, 140, 70), "COASTLINE"),
        ("pine-ridge", (900, 600), (18, 46, 30), (170, 210, 130), "PINE RIDGE"),
        ("harbor", (900, 600), (28, 24, 54), (230, 110, 150), "HARBOR LIGHTS"),
        ("portrait-orientation", (800, 500), (56, 34, 20), (250, 200, 120), "ROTATED SAMPLE"),
    ]
    paths = []
    for index, (name, size, top, bottom, label) in enumerate(specs):
        image = _gradient(size, top, bottom)
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = size
        for ring in range(6):
            radius = int(width * (0.06 + ring * 0.05))
            draw.ellipse(
                (width // 2 - radius, height // 2 - radius, width // 2 + radius, height // 2 + radius),
                outline=(255, 255, 255, 34),
                width=3,
            )
        for stripe in range(9):
            x = int(width * (0.08 + stripe * 0.105))
            draw.rectangle((x, int(height * 0.62), x + width // 30, height), fill=(0, 0, 0, 45))
        draw.text((width // 14, int(height * 0.08)), label, font=load_font(width // 22), fill=(255, 255, 255, 220))
        draw.text(
            (width // 14, int(height * 0.08) + width // 22 + 10),
            f"sample frame {index + 1}",
            font=load_font(width // 55),
            fill=(255, 255, 255, 150),
        )
        path = directory / f"{name}.jpg"
        if name.startswith("portrait"):
            exif = Image.Exif()
            exif[0x0112] = 6  # stored landscape, displayed portrait
            image.save(path, quality=94, exif=exif.tobytes())
        else:
            image.save(path, quality=94)
        paths.append(path)
    return paths


def make_demo_logo(destination: Path) -> None:
    """Create a small translucent logo with a ring and monogram."""
    logo = Image.new("RGBA", (320, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.rounded_rectangle((2, 2, 318, 138), radius=24, fill=(12, 12, 18, 190), outline=(255, 255, 255, 160), width=3)
    draw.ellipse((22, 26, 110, 114), outline=(255, 183, 3, 255), width=6)
    draw.ellipse((44, 48, 88, 92), fill=(255, 183, 3, 220))
    draw.text((130, 42), "MINI", font=load_font(38), fill=(255, 255, 255, 245))
    draw.text((130, 82), "MEDIA", font=load_font(22), fill=(255, 183, 3, 235))
    logo.save(destination)


def run_demo() -> int:
    """Generate sample photos and run a four-worker batch."""
    require_pillow()
    workdir = Path(tempfile.mkdtemp(prefix="watermark-demo-"))
    photos_dir = workdir / "photos"
    photos_dir.mkdir()
    outdir = workdir / "watermarked"
    print("Watermarking Application demo")
    print(f"  workspace: {workdir}")

    photos = make_demo_photos(photos_dir)
    logo = workdir / "logo.png"
    make_demo_logo(logo)
    print(f"  generated: {len(photos)} photos + logo.png")

    options = WatermarkOptions(
        text="(c) MiniMedia 2026",
        logo=logo,
        opacity=0.32,
        position="bottom-right",
        logo_position="bottom-left",
        scale=0.16,
        font_size=30,
        tile=False,
    )
    started = time.perf_counter()
    results = run_batch(photos, outdir, options, workers=4, quality=92)
    elapsed = time.perf_counter() - started
    print(f"  batch    : {len(results)} images with 4 worker threads in {elapsed * 1000:.0f} ms")
    for result in results:
        status = "OK " if result.ok else "ERR"
        detail = result.detail if result.ok else result.error
        print(f"    [{status}] {result.source.name:<28} {detail}")

    # Tiled watermark, to show the other placement mode.
    tiled_options = WatermarkOptions(
        text="SAMPLE", opacity=0.18, tile=True, font_size=24, angle=0, shadow=False
    )
    tiled = process_file(photos[0], outdir / "tiled", tiled_options)
    print(f"  tiled    : {'OK' if tiled.ok else 'ERR'} {tiled.output.name if tiled.output else tiled.error}")

    portrait = outdir / "portrait-orientation_watermarked.jpg"
    upright_size = ""
    if portrait.exists():
        with Image.open(portrait) as check:
            upright_size = f"{check.width}x{check.height}"
            orientation = check.getexif().get(0x0112, 1)
    else:
        orientation = None

    checks = [
        all(result.ok for result in results),
        tiled.ok,
        portrait.exists() and upright_size == "500x800",
        orientation == 1,
        all(result.output and result.output.stat().st_size > 1000 for result in results if result.output),
    ]
    print(f"  EXIF     : stored 800x500 with orientation=6 -> saved upright {upright_size}, tag={orientation}")
    print(f"  checks   : {sum(checks)}/{len(checks)} passed")
    print("Demo complete: inspect the watermarked JPEGs in the workspace.")
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add text and/or logo watermarks to images in parallel, preserving EXIF orientation.",
        epilog="Example: python3 solution.py photos/ --text '(c) Studio' --logo logo.png --position bottom-right",
    )
    parser.add_argument("inputs", nargs="*", metavar="IMAGE_OR_DIR", help="image files or directories")
    parser.add_argument("--text", help="text watermark")
    parser.add_argument("--logo", metavar="FILE", help="logo image (PNG with transparency works best)")
    parser.add_argument("--outdir", default="watermarked", metavar="DIR", help="output directory (default: watermarked)")
    parser.add_argument("--position", default="bottom-right", choices=POSITIONS, help="text anchor (default: bottom-right)")
    parser.add_argument("--logo-position", default="top-left", choices=POSITIONS, help="logo anchor (default: top-left)")
    parser.add_argument("--opacity", type=float, default=0.25, help="watermark opacity 0.0-1.0 (default: 0.25)")
    parser.add_argument("--scale", type=float, default=0.18, help="logo width as a fraction of image width (default: 0.18)")
    parser.add_argument("--angle", type=float, default=0.0, help="rotation in degrees (default: 0)")
    parser.add_argument("--font-size", type=int, default=34, help="text size in pixels (default: 34)")
    parser.add_argument("--tile", action="store_true", help="repeat the text across the whole image")
    parser.add_argument("--margin", type=int, default=24, help="edge margin in pixels (default: 24)")
    parser.add_argument("--workers", type=int, default=4, help="thread pool size (default: 4)")
    parser.add_argument("--quality", type=int, default=92, help="JPEG/WebP quality 1-100 (default: 92)")
    parser.add_argument("--demo", action="store_true", help="generate sample photos and watermark them")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    require_pillow()

    if args.demo:
        return run_demo()

    if not args.text and not args.logo and not args.inputs and sys.stdin.isatty():
        try:
            raw = input("Watermark text (leave blank to use a logo): ").strip()
            if raw:
                args.text = raw
            else:
                logo_path = input("Logo image path: ").strip().strip("'\"")
                if logo_path:
                    args.logo = logo_path
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130

    if not args.text and not args.logo:
        parser.error("give at least one of --text or --logo")
    if not 0.0 <= args.opacity <= 1.0:
        parser.error("--opacity must be between 0 and 1")
    if not 0.0 < args.scale <= 1.0:
        parser.error("--scale must be between 0 and 1")
    if args.logo and not Path(args.logo).is_file():
        parser.error(f"logo not found: {args.logo}")

    inputs = args.inputs
    if not inputs:
        if not sys.stdin.isatty():
            parser.error("no images given (try --demo)")
        try:
            raw = input("Image folder or files (space separated): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if not raw:
            parser.error("no images given")
        inputs = raw.split()

    try:
        paths = collect_inputs(inputs)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    options = WatermarkOptions(
        text=args.text,
        logo=Path(args.logo).expanduser() if args.logo else None,
        opacity=args.opacity,
        position=args.position,
        logo_position=args.logo_position,
        scale=args.scale,
        angle=args.angle,
        tile=args.tile,
        margin=args.margin,
        font_size=args.font_size,
    )
    outdir = Path(args.outdir)
    started = time.perf_counter()
    results = run_batch(paths, outdir, options, args.workers, args.quality)
    elapsed = time.perf_counter() - started

    failures = 0
    for result in results:
        if result.ok:
            print(f"{result.source} -> {result.output} ({result.seconds * 1000:.0f} ms)")
        else:
            failures += 1
            print(f"FAILED {result.source}: {result.error}", file=sys.stderr)
    print(f"Processed {len(results) - failures}/{len(results)} images in {elapsed:.2f}s -> {outdir}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
