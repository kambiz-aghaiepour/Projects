#!/usr/bin/env python3
"""Build optimised animated GIFs from images or a short video.

Images are normalised to a common canvas, optionally reduced to a shared
palette to prevent flicker, and saved with per-frame durations and loop count.
When ``ffmpeg`` is installed, ``--video`` extracts frames from a clip first.

Examples::

    python3 solution.py frames/*.png --out spin.gif --duration 80
    python3 solution.py --video clip.mp4 --fps 12 --max-seconds 5
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

SUPPORTED = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
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
                from PIL import ImageFont as FontModule
                return FontModule.truetype(candidate, size)
            except OSError:
                continue
    from PIL import ImageFont as FontModule
    try:
        return FontModule.load_default(size=size)
    except TypeError:
        return FontModule.load_default()


def collect_images(inputs: Sequence[str]) -> list[Path]:
    """Expand file/directory arguments into a sorted image list."""
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED))
        elif path.is_file() and path.suffix.lower() in SUPPORTED:
            paths.append(path)
        elif path.is_file():
            raise ValueError(f"unsupported image type: {path}")
        else:
            raise FileNotFoundError(f"no such file or directory: {path}")
    if not paths:
        raise ValueError("no supported images found")
    return paths


def fit_frame(image: "Image.Image", size: tuple[int, int], mode: str, background: str = "#121218") -> "Image.Image":
    """Resize an image to the GIF canvas using contain, cover or stretch."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    if mode == "stretch":
        return image.resize(size, Image.Resampling.LANCZOS)
    if mode == "cover":
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    canvas = Image.new("RGB", size, background)
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    canvas.paste(copy, ((size[0] - copy.width) // 2, (size[1] - copy.height) // 2))
    return canvas


def load_frames(paths: Sequence[Path], size: tuple[int, int], fit: str) -> list["Image.Image"]:
    """Load every image and fit it to the canvas."""
    frames: list["Image.Image"] = []
    for path in paths:
        try:
            with Image.open(path) as opened:
                frames.append(fit_frame(opened, size, fit))
        except (OSError, ValueError) as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
    if not frames:
        raise ValueError("none of the images could be read")
    return frames


def extract_video_frames(
    video: Path,
    workdir: Path,
    fps: float,
    max_seconds: float,
    width: int,
    start: float = 0.0,
) -> list["Image.Image"]:
    """Extract frames from a video with ffmpeg and return them in order."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for --video; install it or use image inputs")
    if not video.is_file():
        raise FileNotFoundError(f"no such video: {video}")
    pattern = workdir / "frame-%05d.png"
    scale = f"scale={width}:-2:flags=lanczos" if width > 0 else "scale=iw:ih"
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-i", str(video),
        "-t", f"{max(0.1, max_seconds):.3f}",
        "-vf", f"fps={max(0.1, fps):g},{scale}",
        str(pattern),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        message = (result.stderr or "unknown ffmpeg error").strip().splitlines()[-1]
        raise RuntimeError(f"ffmpeg failed: {message}")
    extracted = sorted(workdir.glob("frame-*.png"))
    if not extracted:
        raise RuntimeError("ffmpeg produced no frames (is the clip shorter than the start offset?)")
    frames = []
    for path in extracted:
        with Image.open(path) as opened:
            frames.append(opened.convert("RGB"))
    return frames


def build_palette(frames: Sequence["Image.Image"], colors: int) -> "Image.Image":
    """Build one shared palette from a contact sheet of all frames."""
    columns = min(8, len(frames))
    rows = (len(frames) + columns - 1) // columns
    thumb_w, thumb_h = 120, max(1, int(120 * frames[0].height / frames[0].width))
    sheet = Image.new("RGB", (columns * thumb_w, rows * thumb_h), "#000000")
    for index, frame in enumerate(frames):
        thumb = frame.resize((thumb_w, thumb_h), Image.Resampling.BILINEAR)
        sheet.paste(thumb, ((index % columns) * thumb_w, (index // columns) * thumb_h))
    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def quantize_frames(frames: Sequence["Image.Image"], colors: int, global_palette: bool) -> list["Image.Image"]:
    """Convert RGB frames to paletted frames for GIF encoding."""
    if global_palette:
        palette = build_palette(frames, colors)
        return [
            frame.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
            for frame in frames
        ]
    return [
        frame.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        for frame in frames
    ]


def write_gif(
    frames: Sequence["Image.Image"],
    destination: Path,
    duration: int = 100,
    loop: int = 0,
    colors: int = 128,
    global_palette: bool = True,
    optimize: bool = True,
) -> tuple[int, int, int, int]:
    """Quantize and save frames; return (frame_count, bytes, width, height)."""
    if not frames:
        raise ValueError("no frames to write")
    if not 2 <= colors <= 256:
        raise ValueError("colours must be between 2 and 256")
    paletted = quantize_frames(frames, colors, global_palette)
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = frames[0].size
    paletted[0].save(
        destination,
        save_all=True,
        append_images=paletted[1:],
        duration=max(20, int(duration)),
        loop=max(0, int(loop)),
        optimize=optimize,
        disposal=2,
    )
    return len(paletted), destination.stat().st_size, width, height


def make_demo_frames(size: tuple[int, int], count: int = 24) -> list["Image.Image"]:
    """Draw a deterministic bouncing-ball animation."""
    width, height = size
    frames: list["Image.Image"] = []
    for index in range(count):
        t = index / count
        image = Image.new("RGB", size)
        pixels = image.load()
        # Vertical gradient background.
        for y in range(height):
            ratio = y / max(1, height - 1)
            pixels_row = (int(12 + 18 * ratio), int(14 + 10 * ratio), int(28 + 40 * ratio))
            for x in range(width):
                pixels[x, y] = pixels_row
        draw = ImageDraw.Draw(image, "RGBA")

        # Motion arc for the bouncing ball.
        angle = 2 * 3.141592653589793 * t
        cx = int(width * (0.15 + 0.70 * t))
        cy = int(height * (0.72 - 0.42 * abs(3.141592653589793 * t - 1.5707963267948966) / 1.5707963267948966))
        radius = int(min(width, height) * 0.085)
        for trail in range(6):
            trail_t = max(0.0, t - trail * 0.012)
            tx = int(width * (0.15 + 0.70 * trail_t))
            ty = int(height * (0.72 - 0.42 * abs(3.141592653589793 * trail_t - 1.5707963267948966) / 1.5707963267948966))
            alpha = 90 - trail * 14
            draw.ellipse((tx - radius, ty - radius, tx + radius, ty + radius), fill=(255, 183, 3, alpha))

        # Ground line and shadow.
        ground = int(height * 0.80)
        draw.line((0, ground, width, ground), fill=(255, 255, 255, 45), width=2)
        shadow_width = radius * (1.4 - 0.4 * abs(cy - ground) / max(1, ground))
        draw.ellipse(
            (cx - shadow_width, ground - radius * 0.18, cx + shadow_width, ground + radius * 0.18),
            fill=(0, 0, 0, 90),
        )
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 183, 3, 255))
        draw.ellipse((cx - radius // 3, cy - radius // 3, cx + radius // 4, cy + radius // 4), fill=(255, 240, 200, 230))

        # Orbiting ring.
        orbit = int(min(width, height) * 0.30)
        ox = width // 2 + int(orbit * 0.9 * (1 - 2 * abs(t - 0.5)))
        draw.ellipse((ox - 12, int(height * 0.28) - 12, ox + 12, int(height * 0.28) + 12), outline=(110, 231, 183, 200), width=3)

        label_size = max(14, width // 32)
        label_font = load_font(label_size)
        small_font = load_font(max(10, width // 64))
        draw.text((24, 20), "GIF CREATOR", font=label_font, fill=(240, 240, 245, 235))
        draw.text((24, 20 + label_size + 6), "bouncing ball · 24 frames", font=small_font, fill=(180, 180, 195, 190))
        draw.text((width - 24, height - 24), f"{index + 1:02d}/{count}", font=small_font, fill=(200, 200, 210, 210), anchor="rs")
        frames.append(image)
    return frames


def make_demo_video(destination: Path) -> bool:
    """Render a short test clip for the video-to-GIF path."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24",
        "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, timeout=60, check=False)
    return result.returncode == 0 and destination.exists()


def run_demo() -> int:
    """Generate frames, write two GIFs and verify both pipelines."""
    require_pillow()
    workdir = Path(tempfile.mkdtemp(prefix="gif-creator-demo-"))
    print("GIF Creator demo")
    print(f"  workspace: {workdir}")

    frames = make_demo_frames((480, 360), count=24)
    gif_path = workdir / "bouncing-ball.gif"
    count, size, width, height = write_gif(
        frames, gif_path, duration=80, loop=0, colors=96, global_palette=True, optimize=True
    )
    print(f"  images   : 24 synthesised frames -> {gif_path.name}")
    print(f"             {count} frames, {width}x{height}, {size / 1024:.1f} KiB, 80 ms/frame, loop forever")

    # Verify what was actually encoded.
    with Image.open(gif_path) as check:
        encoded_frames = getattr(check, "n_frames", 1)
        encoded_size = check.size
        encoded_duration = check.info.get("duration")
    print(f"  verified : n_frames={encoded_frames}, size={encoded_size[0]}x{encoded_size[1]}, duration={encoded_duration} ms")

    video_ok = None
    overlay = ""
    clip = workdir / "sample.mp4"
    if make_demo_video(clip):
        try:
            video_frames = extract_video_frames(clip, workdir, fps=12, max_seconds=2, width=360)
            video_gif = workdir / "video-sample.gif"
            vcount, vsize, vw, vh = write_gif(
                video_frames, video_gif, duration=83, loop=0, colors=64, global_palette=True
            )
            video_ok = True
            overlay = f"{vcount} frames, {vw}x{vh}, {vsize / 1024:.1f} KiB from sample.mp4"
        except (RuntimeError, OSError) as exc:
            video_ok = False
            overlay = f"failed: {exc}"
    else:
        overlay = "skipped (ffmpeg not available)"
    print(f"  video    : {overlay}")

    checks = [
        count == 24,
        encoded_frames == 24,
        encoded_size == (480, 360),
        encoded_duration == 80,
        size > 10_000,
        video_ok is not False,
    ]
    print(f"  checks   : {sum(checks)}/{len(checks)} passed")
    print("Demo complete: open bouncing-ball.gif in any viewer.")
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine images (or a video) into an optimised animated GIF.",
        epilog="Example: python3 solution.py frames/ --out animation.gif --duration 80 --colors 128",
    )
    parser.add_argument("images", nargs="*", metavar="IMAGE_OR_DIR", help="image files or directories")
    parser.add_argument("--video", metavar="FILE", help="extract frames from a video with ffmpeg")
    parser.add_argument("--out", default="animation.gif", metavar="PATH", help="output GIF (default: animation.gif)")
    parser.add_argument("--duration", type=int, default=100, metavar="MS", help="milliseconds per frame (default: 100)")
    parser.add_argument("--loop", type=int, default=0, metavar="N", help="0 = forever, N = extra repeats (default: 0)")
    parser.add_argument("--colors", type=int, default=128, help="palette size 2-256 (default: 128)")
    parser.add_argument("--width", type=int, default=480, help="canvas width (default: 480)")
    parser.add_argument("--height", type=int, default=360, help="canvas height (default: 360)")
    parser.add_argument("--fit", choices=["cover", "contain", "stretch"], default="contain", help="how images fill the canvas (default: contain)")
    parser.add_argument("--per-frame-palette", action="store_true", help="use a separate palette per frame instead of one shared palette")
    parser.add_argument("--no-optimize", action="store_true", help="disable GIF frame optimisation")
    parser.add_argument("--fps", type=float, default=12, help="video sampling rate (default: 12)")
    parser.add_argument("--start", type=float, default=0.0, help="video start offset in seconds (default: 0)")
    parser.add_argument("--max-seconds", type=float, default=6.0, help="maximum video seconds to convert (default: 6)")
    parser.add_argument("--demo", action="store_true", help="synthesise frames and write demo GIFs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    require_pillow()

    if args.demo:
        return run_demo()

    if args.video and args.images:
        parser.error("give either images or --video, not both")
    if not args.video and not args.images:
        if not sys.stdin.isatty():
            parser.error("no images given (try --demo)")
        try:
            raw = input("Image folder or files (space separated): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if not raw:
            parser.error("no images given")
        args.images = raw.split()
    if args.width < 32 or args.height < 32:
        parser.error("--width and --height must be at least 32")
    if not 2 <= args.colors <= 256:
        parser.error("--colors must be between 2 and 256")

    size = (args.width, args.height)
    try:
        if args.video:
            with tempfile.TemporaryDirectory(prefix="gif-video-") as raw_temp:
                tempdir = Path(raw_temp)
                frames = extract_video_frames(Path(args.video).expanduser(), tempdir, args.fps, args.max_seconds, args.width, args.start)
                frames = [fit_frame(frame, size, args.fit) for frame in frames]
                count, written, width, height = write_gif(
                    frames, Path(args.out), args.duration, args.loop, args.colors,
                    not args.per_frame_palette, not args.no_optimize,
                )
        else:
            paths = collect_images(args.images)
            frames = load_frames(paths, size, args.fit)
            count, written, width, height = write_gif(
                frames, Path(args.out), args.duration, args.loop, args.colors,
                not args.per_frame_palette, not args.no_optimize,
            )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {args.out}: {count} frames, {width}x{height}, {written / 1024:.1f} KiB")
    print(f"Timing: {args.duration} ms/frame, loop={'forever' if args.loop == 0 else args.loop}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
