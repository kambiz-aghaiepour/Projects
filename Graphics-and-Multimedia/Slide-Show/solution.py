#!/usr/bin/env python3
"""Slide show builder: animated GIF (with transitions) and a standalone HTML viewer.

The program takes a set of images, fits them onto a common canvas, and produces

* an animated GIF that plays each slide and cross-fades / wipes between them, and
* a single self-contained HTML file (images embedded as data URIs) with
  keyboard navigation, autoplay, captions and CSS fade/wipe transitions.

Both outputs are optional; at least one is written.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover - exercised only without Pillow
    Image = None  # type: ignore[assignment]

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
)


def require_pillow() -> None:
    """Exit with a helpful message when Pillow is missing."""
    if Image is None:
        raise SystemExit("Pillow is required: pip install -r requirements.txt")


def load_font(size: int) -> "ImageFont.ImageFont":
    """Return a scalable font, falling back to Pillow's bundled default."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def fit_on_canvas(image: "Image.Image", size: tuple[int, int]) -> "Image.Image":
    """Letterbox ``image`` on a darkened, blurred cover background."""
    width, height = size
    source = ImageOps.exif_transpose(image).convert("RGB")

    # An image that already matches the canvas aspect ratio fills it edge to edge.
    if abs(source.width / source.height - width / height) < 0.02:
        return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)

    backdrop = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=max(6, width // 70)))
    backdrop = Image.eval(backdrop, lambda value: int(value * 0.55))
    canvas = backdrop.convert("RGB")

    contained = source.copy()
    contained.thumbnail((width - 32, height - 32), Image.Resampling.LANCZOS)
    canvas.paste(contained, ((width - contained.width) // 2, (height - contained.height) // 2))
    return canvas


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> "Image.Image":
    """Create a vertical gradient image."""
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        t = y / max(1, height - 1)
        pixels[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize(size, Image.Resampling.BILINEAR)


def make_sample_slides(directory: Path, size: tuple[int, int], count: int = 4) -> list[Path]:
    """Draw deterministic demo slides and return their paths."""
    palettes = [
        ((14, 32, 64), (232, 119, 34), "NORTHERN LIGHTS", "Aurora over the fjord"),
        ((30, 12, 48), (240, 90, 140), "CITY AFTERGLOW", "Rooftops at blue hour"),
        ((10, 40, 38), (90, 220, 170), "TIDAL FOREST", "Where the river meets the sea"),
        ((48, 20, 16), (255, 190, 80), "DESERT NOON", "Dunes and long shadows"),
    ]
    paths: list[Path] = []
    width, height = size
    for index in range(min(count, len(palettes))):
        top, bottom, title, caption = palettes[index]
        image = _gradient(size, top, bottom)
        draw = ImageDraw.Draw(image, "RGBA")

        # Soft translucent geometry, varied per slide.
        for ring in range(5):
            radius = int(width * (0.10 + ring * 0.075))
            cx = int(width * (0.22 + 0.17 * index)) + ring * 9
            cy = int(height * (0.32 + 0.06 * (index % 2)))
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                outline=(255, 255, 255, 40),
                width=max(2, width // 300),
            )
        horizon = int(height * 0.72)
        draw.rectangle((0, horizon, width, height), fill=(0, 0, 0, 70))
        for step in range(7):
            x = int(width * (0.55 + step * 0.06))
            h = int(height * (0.10 + 0.035 * ((step * index) % 4)))
            draw.rectangle((x, horizon - h, x + width // 22, horizon), fill=(0, 0, 0, 55))

        title_size = max(22, width // 18)
        title_font = load_font(title_size)
        caption_font = load_font(max(14, width // 48))
        draw.text((width // 18, int(height * 0.77)), title, font=title_font, fill=(255, 255, 255, 235))
        draw.text(
            (width // 18, int(height * 0.77) + title_size + 12),
            caption,
            font=caption_font,
            fill=(255, 255, 255, 170),
        )
        draw.text(
            (width - width // 16, height - height // 20),
            f"{index + 1:02d}",
            font=load_font(max(12, width // 60)),
            fill=(255, 255, 255, 120),
            anchor="rs",
        )

        slug = title.lower().replace(" ", "-")
        path = directory / f"{index + 1:02d}-{slug}.png"
        image.save(path)
        paths.append(path)
    return paths


def _transition_mask(kind: str, size: tuple[int, int], progress: float) -> "Image.Image":
    """Build an L-mode reveal mask for one transition frame."""
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    progress = min(1.0, max(0.0, progress))

    if kind == "wipe":
        edge = int(width * progress)
        feather = max(1, width // 80)
        if edge > 0:
            draw.rectangle((0, 0, edge, height), fill=255)
        for offset in range(feather):
            alpha = int(255 * (1 - offset / feather))
            x = edge + offset
            if x < width:
                draw.line((x, 0, x, height), fill=alpha)
    elif kind == "blinds":
        bands = 10
        band_height = height / bands
        for band in range(bands):
            stagger = 0.35 * (band / bands)
            local = min(1.0, max(0.0, (progress - stagger) / (1 - 0.35)))
            top = band * band_height
            reveal = band_height * local
            draw.rectangle((0, top, width, top + reveal), fill=255)
    elif kind == "star":
        cx, cy = width / 2, height / 2
        outer = math.hypot(width, height) / 2 * progress
        inner = outer * 0.45
        points = []
        for step in range(16):
            angle = -math.pi / 2 + step * math.pi / 8
            radius = outer if step % 2 == 0 else inner
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        if len(points) >= 3:
            draw.polygon(points, fill=255)
    else:  # fade uses a flat mask
        draw.rectangle((0, 0, width, height), fill=255)
    return mask


def transition_frames(
    first: "Image.Image",
    second: "Image.Image",
    kind: str,
    steps: int,
) -> list["Image.Image"]:
    """Return intermediate frames morphing ``first`` into ``second``."""
    if kind == "fade":
        return [Image.blend(first, second, step / (steps + 1)) for step in range(1, steps + 1)]
    frames = []
    for step in range(1, steps + 1):
        mask = _transition_mask(kind, first.size, step / (steps + 1))
        frames.append(Image.composite(second, first, mask))
    return frames


@dataclass
class Slide:
    """One rendered slide plus the caption drawn from its file name."""

    image: "Image.Image"
    caption: str
    source: Path


def load_slides(paths: Iterable[Path], size: tuple[int, int]) -> list[Slide]:
    """Load and fit every image; skip unreadable files with a warning."""
    slides: list[Slide] = []
    for path in paths:
        try:
            with Image.open(path) as opened:
                fitted = fit_on_canvas(opened, size)
        except (OSError, ValueError) as exc:
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
            continue
        caption = path.stem.replace("_", " ").replace("-", " ").strip().title()
        slides.append(Slide(fitted, caption, path))
    if not slides:
        raise ValueError("no readable images found")
    return slides


def collect_images(inputs: Sequence[str]) -> list[Path]:
    """Expand files and directories into a sorted list of image paths."""
    found: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            found.extend(
                sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES)
            )
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(f"no such file or directory: {path}")
    return found


def build_gif(
    slides: Sequence[Slide],
    destination: Path,
    hold_ms: int,
    transition: str,
    transition_ms: int,
    steps: int,
    colors: int,
) -> tuple[int, int]:
    """Write the animated GIF and return (frame count, byte size)."""
    step_ms = max(20, transition_ms // steps)
    frames: list["Image.Image"] = []
    durations: list[int] = []
    transitions = ["fade", "wipe", "blinds"] if transition == "cycle" else [transition]

    for index, slide in enumerate(slides):
        if index:
            previous = slides[index - 1].image
            kind = transitions[(index - 1) % len(transitions)]
            frames.extend(transition_frames(previous, slide.image, kind, steps))
            durations.extend([step_ms] * steps)
        frames.append(slide.image)
        durations.append(hold_ms)

    # Close the loop with a transition back to the first slide.
    if len(slides) > 1:
        kind = transitions[(len(slides) - 1) % len(transitions)]
        frames.extend(transition_frames(slides[-1].image, slides[0].image, kind, steps))
        durations.extend([step_ms] * steps)

    paletted = [frame.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT) for frame in frames]
    destination.parent.mkdir(parents=True, exist_ok=True)
    paletted[0].save(
        destination,
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    return len(paletted), destination.stat().st_size


def _data_uri(path: Path, size: tuple[int, int], quality: int = 82) -> str:
    """Embed a slide into the HTML as a compact JPEG data URI."""
    with Image.open(path) as opened:
        fitted = fit_on_canvas(opened, size)
    buffer = io.BytesIO()
    fitted.save(buffer, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; --accent: #ffb703; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0b0b10; color: #f5f5f7;
         font: 15px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif; }}
  .shell {{ width: min(100vw, 1080px); padding: 18px; }}
  .stage {{ position: relative; aspect-ratio: {width} / {height}; overflow: hidden;
           border-radius: 16px; background: #000; box-shadow: 0 24px 70px rgba(0,0,0,.6); }}
  .slide {{ position: absolute; inset: 0; opacity: 0; }}
  .slide img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .slide.active {{ opacity: 1; z-index: 2; }}
  .slide.outgoing {{ opacity: 1; z-index: 1; }}
  .slide.active.tx-fade {{ animation: fadeIn var(--tx) ease both; }}
  .slide.active.tx-wipe {{ animation: wipeIn var(--tx) cubic-bezier(.4,0,.2,1) both; }}
  @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  @keyframes wipeIn {{ from {{ clip-path: inset(0 100% 0 0); }} to {{ clip-path: inset(0 0 0 0); }} }}
  .caption {{ position: absolute; left: 24px; bottom: 20px; z-index: 3;
             padding: 8px 14px; border-radius: 10px; background: rgba(0,0,0,.45);
             backdrop-filter: blur(6px); font-size: 15px; letter-spacing: .02em; }}
  .hud {{ display: flex; align-items: center; gap: 14px; margin-top: 14px; }}
  button {{ appearance: none; border: 1px solid #33333f; background: #17171f; color: inherit;
           border-radius: 10px; padding: 9px 13px; font: inherit; cursor: pointer; }}
  button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .dots {{ display: flex; gap: 7px; margin-left: auto; }}
  .dot {{ width: 9px; height: 9px; padding: 0; border-radius: 50%; background: #3a3a48; border: 0; }}
  .dot.on {{ background: var(--accent); }}
  .hint {{ color: #8b8b9a; font-size: 12.5px; margin-top: 10px; text-align: center; }}
  select {{ background: #17171f; color: inherit; border: 1px solid #33333f; border-radius: 10px; padding: 9px; }}
</style>
</head>
<body>
<div class="shell">
  <div class="stage" id="stage">
    {slides}
    <div class="caption" id="caption"></div>
  </div>
  <div class="hud">
    <button id="prev" title="Previous slide">&#8592; Prev</button>
    <button id="toggle" title="Play / pause">Pause</button>
    <button id="next" title="Next slide">Next &#8594;</button>
    <label><span class="hint">Effect</span>
      <select id="effect"><option value="fade">fade</option><option value="wipe">wipe</option></select>
    </label>
    <div class="dots" id="dots"></div>
  </div>
  <div class="hint">Arrow keys navigate &middot; Space pauses &middot; images are embedded, this file works offline</div>
</div>
<script>
const slides = [...document.querySelectorAll('.slide')];
const captions = {captions};
const stage = document.getElementById('stage');
const caption = document.getElementById('caption');
const dots = document.getElementById('dots');
let current = 0, playing = true, timer = null, tx = 'fade', outgoingTimer = null;
const DURATION = {hold_ms};
const TRANSITION = {transition_ms};

slides.forEach((_, index) => {{
  const dot = document.createElement('button');
  dot.className = 'dot' + (index === 0 ? ' on' : '');
  dot.setAttribute('aria-label', 'Slide ' + (index + 1));
  dot.addEventListener('click', () => show(index, true));
  dots.appendChild(dot);
}});

function show(index, manual = false) {{
  index = (index + slides.length) % slides.length;
  const incoming = slides[index];
  const previous = slides[current];
  clearTimeout(outgoingTimer);
  slides.forEach((slide, i) => {{
    slide.classList.remove('tx-fade', 'tx-wipe', 'outgoing');
    if (i !== index) slide.classList.remove('active');
  }});
  if (previous && previous !== incoming) previous.classList.add('outgoing');
  incoming.classList.add('active', 'tx-' + tx);
  stage.style.setProperty('--tx', TRANSITION + 'ms');
  current = index;
  caption.textContent = captions[index] || '';
  [...dots.children].forEach((dot, i) => dot.classList.toggle('on', i === index));
  outgoingTimer = setTimeout(() => slides.forEach((slide) => slide.classList.remove('outgoing')), TRANSITION);
  if (manual) restart();
}}

function restart() {{
  clearInterval(timer);
  if (playing) timer = setInterval(() => show(current + 1), DURATION + TRANSITION);
}}

document.getElementById('next').onclick = () => show(current + 1, true);
document.getElementById('prev').onclick = () => show(current - 1, true);
document.getElementById('toggle').onclick = (event) => {{
  playing = !playing;
  event.target.textContent = playing ? 'Pause' : 'Play';
  restart();
}};
document.getElementById('effect').onchange = (event) => {{ tx = event.target.value; }};

document.addEventListener('keydown', (event) => {{
  if (event.key === 'ArrowRight') show(current + 1, true);
  else if (event.key === 'ArrowLeft') show(current - 1, true);
  else if (event.key === ' ') {{ event.preventDefault(); document.getElementById('toggle').click(); }}
}});

show(0);
restart();
</script>
</body>
</html>
"""


def build_html(slides: Sequence[Slide], destination: Path, size: tuple[int, int], hold_ms: int, transition_ms: int) -> int:
    """Write the self-contained HTML viewer and return its byte size."""
    blocks = []
    captions = []
    for index, slide in enumerate(slides):
        uri = _data_uri(slide.source, size)
        active = " active tx-fade" if index == 0 else ""
        blocks.append(
            f'<figure class="slide{active}" data-index="{index}">'
            f'<img src="{uri}" alt="{html.escape(slide.caption, quote=True)}"></figure>'
        )
        captions.append(slide.caption)
    captions_js = json.dumps(captions)
    document = HTML_TEMPLATE.format(
        title="Slide Show",
        width=size[0],
        height=size[1],
        slides="\n    ".join(blocks),
        captions=captions_js,
        hold_ms=hold_ms,
        transition_ms=transition_ms,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination.stat().st_size


def run_demo() -> int:
    """Generate sample images plus a GIF and an HTML viewer in a temp dir."""
    require_pillow()
    size = (640, 480)
    workdir = Path(tempfile.mkdtemp(prefix="slide-show-demo-"))
    images_dir = workdir / "images"
    images_dir.mkdir()
    print("Slide Show demo")
    print(f"  workspace : {workdir}")

    paths = make_sample_slides(images_dir, size, count=4)
    print(f"  generated : {len(paths)} sample slides ({size[0]}x{size[1]})")
    for path in paths:
        print(f"              {path.name}  {path.stat().st_size / 1024:.1f} KiB")

    slides = load_slides(paths, size)
    gif_path = workdir / "slideshow.gif"
    frames, gif_bytes = build_gif(slides, gif_path, hold_ms=1200, transition="cycle", transition_ms=600, steps=6, colors=96)
    print(f"  GIF       : {gif_path.name}  {frames} frames  {gif_bytes / 1024:.1f} KiB")

    html_path = workdir / "slideshow.html"
    html_bytes = build_html(slides, html_path, size, hold_ms=3200, transition_ms=650)
    print(f"  HTML      : {html_path.name}  {html_bytes / 1024:.1f} KiB (self-contained, {len(slides)} slides)")
    print(f"  transitions: {', '.join(['fade', 'wipe', 'blinds'])} (GIF cycles all three)")
    print("Demo complete: open the HTML file in a browser or the GIF in any image viewer.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turn images into an animated GIF and a self-contained HTML slide show.",
        epilog="With no images and no --demo you will be prompted for a folder.",
    )
    parser.add_argument("images", nargs="*", metavar="IMAGE_OR_DIR", help="image files or directories")
    parser.add_argument("--gif", metavar="PATH", help="output GIF path (default: <outdir>/slideshow.gif)")
    parser.add_argument("--html", metavar="PATH", help="output HTML path (default: <outdir>/slideshow.html)")
    parser.add_argument("--outdir", default="slideshow_output", metavar="DIR", help="default output directory")
    parser.add_argument("--transition", default="cycle", choices=["fade", "wipe", "blinds", "star", "cycle"], help="GIF transition (default: cycle)")
    parser.add_argument("--hold", type=float, default=2.0, metavar="SECONDS", help="seconds each slide is shown (default: 2.0)")
    parser.add_argument("--transition-ms", type=int, default=700, metavar="MS", help="transition duration in ms (default: 700)")
    parser.add_argument("--steps", type=int, default=8, metavar="N", help="transition frames (default: 8)")
    parser.add_argument("--width", type=int, default=800, help="canvas width (default: 800)")
    parser.add_argument("--height", type=int, default=600, help="canvas height (default: 600)")
    parser.add_argument("--colors", type=int, default=128, help="GIF palette size, 2-256 (default: 128)")
    parser.add_argument("--no-gif", action="store_true", help="skip GIF output")
    parser.add_argument("--no-html", action="store_true", help="skip HTML output")
    parser.add_argument("--demo", action="store_true", help="generate sample slides and both outputs, then exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    require_pillow()

    if args.demo:
        return run_demo()

    if not 2 <= args.colors <= 256:
        parser.error("--colors must be between 2 and 256")
    if args.steps < 1:
        parser.error("--steps must be at least 1")
    if args.width < 64 or args.height < 64:
        parser.error("canvas must be at least 64x64")
    if args.no_gif and args.no_html:
        parser.error("both outputs are disabled; nothing to do")

    inputs = args.images
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
        paths = collect_images(inputs)
        if not paths:
            raise ValueError("no supported images found")
        slides = load_slides(paths, (args.width, args.height))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    outdir = Path(args.outdir)
    gif_path = Path(args.gif) if args.gif else outdir / "slideshow.gif"
    html_path = Path(args.html) if args.html else outdir / "slideshow.html"
    hold_ms = int(args.hold * 1000)

    try:
        if not args.no_gif:
            frames, size = build_gif(slides, gif_path, hold_ms, args.transition, args.transition_ms, args.steps, args.colors)
            print(f"Wrote {gif_path} ({frames} frames, {size / 1024:.1f} KiB)")
        if not args.no_html:
            size = build_html(slides, html_path, (args.width, args.height), hold_ms, args.transition_ms)
            print(f"Wrote {html_path} ({len(slides)} slides, {size / 1024:.1f} KiB)")
    except OSError as exc:
        print(f"Error writing output: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
