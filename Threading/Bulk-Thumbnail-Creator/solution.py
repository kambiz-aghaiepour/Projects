#!/usr/bin/env python3
"""Bulk-convert hundreds of images to thumbnails in the background.

The work is split into two concurrent stages: a fixed pool of resize workers
decodes and shrinks images, and a single renamer thread assigns final names,
collects metadata and writes a JSON manifest.  ``--demo`` generates a
deterministic set of sample images (including one corrupt file) in a temporary
directory and runs the whole pipeline end to end.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from demo import run_demo
from pipeline import (
    FORMAT_EXTENSIONS,
    Summary,
    ThumbnailPipeline,
    discover_images,
    validate_template,
)
from reporting import print_report


def parse_size(text: str) -> tuple[int, int]:
    """Parse a ``WIDTHxHEIGHT`` geometry string."""
    match = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", text)
    if not match:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 200x200")
    width, height = int(match.group(1)), int(match.group(2))
    if width < 1 or height < 1:
        raise argparse.ArgumentTypeError("dimensions must be positive")
    return width, height


def wait_with_status(pipeline: ThumbnailPipeline) -> Summary:
    """Let the main thread show a live status line on a TTY, then collect."""
    if not sys.stderr.isatty():
        return pipeline.wait()
    last = ""
    while not pipeline.done:
        stats = pipeline.stats()
        line = (
            f"  {stats.resized}/{stats.discovered} resized  |  "
            f"{stats.renamed} renamed  |  {stats.failed} failed"
        )
        if line != last:
            sys.stderr.write("\r" + line.ljust(72))
            sys.stderr.flush()
            last = line
        time.sleep(0.1)
    summary = pipeline.wait()
    sys.stderr.write("\r" + " " * 72 + "\r")
    sys.stderr.flush()
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a directory of images to thumbnails using a two-stage "
            "pipeline: concurrent resize workers feed a bounded queue that a "
            "renamer/metadata thread drains."
        ),
        epilog="Run with --demo for self-contained sample images and a full run.",
    )
    parser.add_argument("input", nargs="?", help="directory containing source images")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("thumbnails"),
        help="output directory (default: ./thumbnails)",
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        default=(200, 200),
        metavar="WxH",
        help="maximum thumbnail bounding box (default: 200x200)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help="resize worker threads (default: up to 8)",
    )
    parser.add_argument(
        "--format",
        type=str.lower,
        choices=sorted(name.lower() for name in FORMAT_EXTENSIONS),
        default="jpeg",
        help="thumbnail format (default: jpeg)",
    )
    parser.add_argument(
        "--quality", type=int, default=85, help="JPEG/WebP quality 1-100 (default: 85)"
    )
    parser.add_argument(
        "--name-template",
        default="{stem}_thumb",
        help=(
            "output name pattern using {index}, {stem}, {date}, {width}, {height} "
            "(default: {stem}_thumb)"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="manifest path (default: OUTPUT/manifest.json)",
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="only scan the top level of INPUT"
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit 1 if any individual image fails"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress startup and status chatter"
    )
    parser.add_argument(
        "--demo", action="store_true", help="generate sample images and run the demo"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.input:
        if not sys.stdin.isatty():
            parser.error("INPUT directory is required (or use --demo)")
        try:
            args.input = input("Input directory: ").strip()
        except EOFError:
            parser.error("INPUT directory is required (or use --demo)")
        if not args.input:
            parser.error("INPUT directory is required (or use --demo)")

    source_dir = Path(args.input)
    if not source_dir.is_dir():
        print(f"error: {source_dir} is not a directory", file=sys.stderr)
        return 2

    try:
        validate_template(args.name_template)
    except ValueError as exc:
        parser.error(str(exc))
    if not 1 <= args.quality <= 100:
        parser.error("--quality must be between 1 and 100")
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be between 1 and 32")

    sources = discover_images(source_dir, recursive=not args.no_recursive)
    if not sources:
        print(f"error: no supported images found under {source_dir}", file=sys.stderr)
        return 1

    pipeline = ThumbnailPipeline(
        sources,
        args.output,
        input_root=source_dir,
        size=args.size,
        workers=args.workers,
        image_format=args.format.upper(),
        quality=args.quality,
        name_template=args.name_template,
        report_path=args.report,
    )
    if not args.quiet:
        print(
            f"Found {len(sources)} images; writing {args.format.upper()} thumbnails "
            f"to {args.output} with {args.workers} resize workers."
        )
    pipeline.start()
    summary = wait_with_status(pipeline)
    print_report(summary)

    if summary.renamed == 0 and summary.failed > 0:
        print("error: every image failed; see the manifest for details", file=sys.stderr)
        return 1
    if args.strict and summary.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
