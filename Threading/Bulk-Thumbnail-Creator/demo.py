"""Deterministic sample-image generator and end-to-end demo runner."""

from __future__ import annotations

import json
import random
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline import ThumbnailPipeline, discover_images
from reporting import format_bytes, print_report


def create_demo_images(root: Path, count: int = 20, seed: int = 7) -> int:
    """Write a deterministic mix of JPEG/PNG images plus one corrupt file."""
    rng = random.Random(seed)
    palettes = [
        ((26, 42, 71), (240, 165, 90)),
        ((38, 54, 40), (196, 214, 120)),
        ((70, 30, 50), (232, 140, 150)),
        ((20, 60, 66), (120, 210, 200)),
        ((60, 50, 30), (230, 200, 130)),
    ]
    root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        width = rng.choice((640, 800, 960, 1200))
        height = int(width * rng.choice((0.5625, 0.6667, 0.75)))
        background, accent = palettes[index % len(palettes)]
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        for _ in range(6):
            x0 = rng.randrange(0, width)
            y0 = rng.randrange(0, height)
            x1 = min(width, x0 + rng.randrange(width // 6, width // 2))
            y1 = min(height, y0 + rng.randrange(height // 6, height // 2))
            color = tuple(
                max(0, min(255, channel + rng.randrange(-50, 50))) for channel in accent
            )
            if rng.random() < 0.5:
                draw.ellipse((x0, y0, x1, y1), fill=color)
            else:
                draw.rectangle((x0, y0, x1, y1), fill=color)

        stem = f"IMG_{index + 1:04d}"
        if index % 7 == 3:
            rgba = image.convert("RGBA")
            overlay = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
            ImageDraw.Draw(overlay).rectangle(
                (0, 0, width // 3, height // 3), fill=(255, 255, 255, 70)
            )
            Image.alpha_composite(rgba, overlay).save(root / f"{stem}.png", "PNG")
        elif index % 9 == 5:
            image.convert("L").save(root / f"{stem}.png", "PNG")
        else:
            exif = Image.Exif()
            stamp = f"2024:05:{(index % 28) + 1:02d} 09:{index % 60:02d}:00"
            exif[36867] = stamp
            image.save(root / f"{stem}.jpg", "JPEG", quality=92, exif=exif)

    (root / "IMG_9999_broken.jpg").write_bytes(b"not a jpeg, just demo junk\n" * 20)
    return count + 1


def run_demo() -> int:
    """Generate sample images, run the pipeline, verify the results."""
    with tempfile.TemporaryDirectory(prefix="thumbnail-demo-") as temp_dir:
        root = Path(temp_dir)
        source_dir = root / "photos"
        output_dir = root / "thumbs"
        created = create_demo_images(source_dir)
        sources = discover_images(source_dir)
        print("Bulk thumbnail demo")
        print(
            f"Generated {created} files in {source_dir.name}/ "
            f"({len(sources) - 1} valid images + 1 deliberately corrupt)"
        )
        print(f"Input size: {format_bytes(sum(path.stat().st_size for path in sources))}")

        pipeline = ThumbnailPipeline(
            sources,
            output_dir,
            input_root=source_dir,
            size=(160, 160),
            workers=4,
            image_format="JPEG",
            quality=82,
            name_template="{index:03d}_{stem}_{width}x{height}",
        )
        print("Main thread: free while 4 resize workers and 1 renamer run.\n")
        pipeline.start()

        shown = 0
        last_key: tuple[int, int, int] | None = None
        while not pipeline.done:
            stats = pipeline.stats()
            key = (stats.resized, stats.renamed, stats.failed)
            if key != last_key and shown < 5:
                print(
                    f"  busy: resized {stats.resized}/{stats.discovered}, "
                    f"renamed {stats.renamed}, failed {stats.failed}"
                )
                last_key, shown = key, shown + 1
            time.sleep(0.05)

        summary = pipeline.wait()
        print_report(summary)

        problems: list[str] = []
        for entry in summary.entries:
            path = summary.output_dir / entry["thumbnail"]
            try:
                with Image.open(path) as thumbnail:
                    thumbnail.load()
                    if thumbnail.width > 160 or thumbnail.height > 160:
                        problems.append(f"{path.name}: {thumbnail.size} exceeds 160x160")
            except Exception as exc:  # noqa: BLE001 - demo verification
                problems.append(f"{path.name}: {type(exc).__name__}: {exc}")

        manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
        manifest_ok = len(manifest["thumbnails"]) == summary.renamed
        checks = {
            "20 thumbnails produced": summary.renamed == 20,
            "one corrupt input isolated": summary.failed == 1,
            "all thumbnails open and fit": not problems,
            "manifest matches results": manifest_ok,
        }
        print("\nVerification")
        for label, passed in checks.items():
            print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        if problems:
            for problem in problems[:3]:
                print(f"    {problem}")
        print(f"\nDemo complete: {sum(checks.values())}/{len(checks)} checks passed.")
        return 0 if all(checks.values()) else 1
