#!/usr/bin/env python3
"""Threaded file downloader with a main-thread progress bar.

A background worker streams the file over HTTP and publishes byte-count
events on a queue.  The main thread is the only one that touches the
terminal, so it can render a live bar (percentage, transfer rate, ETA)
without racing the download logic - the Python equivalent of a UI thread
receiving delegate callbacks.

Supports resuming partial downloads with HTTP ``Range`` requests, a
``--quiet`` mode, and a self-contained ``--demo`` that starts a throttled
local HTTP server (including range support) and exercises every path.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.parse
from pathlib import Path

from demo_server import build_payload, demo_server
from downloader import CHUNK_SIZE, download
from progress import human_bytes


def run_demo() -> int:
    """Exercise full download, interrupted + resumed download, and quiet mode."""
    payload = build_payload(3 * 1024 * 1024)
    expected = hashlib.sha256(payload).hexdigest()
    checks: list[bool] = []

    with tempfile.TemporaryDirectory(prefix="progress-demo-") as temp_dir:
        root = Path(temp_dir)
        with demo_server(payload, delay=0.02) as url:
            print("Progress bar demo: worker thread downloads, main thread renders.")
            print(f"Loopback server: {url} ({human_bytes(len(payload))}, throttled)\n")

            print("[1/3] Straight download")
            full = download(url, root / "sample.bin", stream=sys.stdout, label="full download")
            checks.append(full.status == "completed" and full.sha256 == expected)
            print(
                f"  -> {full.status}, {human_bytes(full.bytes_written)} written, "
                f"sha256 {'verified' if full.sha256 == expected else 'MISMATCH'}\n"
            )

            print("[2/3] Interrupted transfer, then resume")
            resumed_path = root / "resumed.bin"
            first = download(
                url,
                resumed_path,
                stream=sys.stdout,
                interrupt_after=1_200_000,
                label="attempt 1",
            )
            part = Path(str(resumed_path) + ".part")
            partial_size = part.stat().st_size if part.exists() else 0
            print(f"  -> {first.status}: {human_bytes(partial_size)} kept in {part.name}")

            second = download(
                url,
                resumed_path,
                resume=True,
                stream=sys.stdout,
                label="resume",
            )
            checks.append(
                second.status == "completed"
                and second.sha256 == expected
                and second.resumed_from == partial_size
            )
            print(
                f"  -> {second.status} from byte {second.resumed_from:,}, "
                f"sha256 {'verified' if second.sha256 == expected else 'MISMATCH'}\n"
            )

            print("[3/3] Quiet mode")
            quiet_result = download(url, root / "quiet.bin", quiet=True, stream=sys.stdout)
            quiet_ok = (
                quiet_result.status == "completed"
                and (root / "quiet.bin").stat().st_size == len(payload)
            )
            checks.append(quiet_ok)
            print(f"  -> no progress lines emitted; file complete: {quiet_ok}")

    print(f"\nDemo complete: {sum(checks)}/{len(checks)} checks passed.")
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download a file on a worker thread while the main thread draws a "
            "CLI progress bar with percentage, transfer rate and ETA."
        ),
        epilog="Run with --demo for a self-contained local-server demonstration.",
    )
    parser.add_argument("url", nargs="?", help="HTTP(S) URL to download")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="destination file (default: the URL's basename)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress the progress bar and chatter"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue from an existing .part file using an HTTP Range request",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        metavar="BYTES",
        help=f"read size per chunk (default: {CHUNK_SIZE})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        metavar="SECONDS",
        help="socket timeout (default: 20)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run the scripted local-server demonstration and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.url:
        if not sys.stdin.isatty():
            parser.error("URL is required unless --demo is used")
        try:
            args.url = input("URL to download: ").strip()
        except EOFError:
            parser.error("URL is required unless --demo is used")
        if not args.url:
            parser.error("URL is required unless --demo is used")
    if args.chunk_size < 1024:
        parser.error("--chunk-size must be at least 1024 bytes")

    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme not in ("http", "https"):
        parser.error("URL must start with http:// or https://")

    destination = args.output or Path(Path(parsed.path).name or "download.bin")
    result = download(
        args.url,
        destination,
        resume=args.resume,
        quiet=args.quiet,
        chunk_size=args.chunk_size,
        timeout=args.timeout,
        stream=sys.stderr,
    )

    if result.status == "completed":
        if not args.quiet:
            print(f"Saved {human_bytes(result.bytes_written)} to {result.path}")
            print(f"SHA-256 {result.sha256}")
        return 0
    if result.status == "cancelled":
        print("Download cancelled.", file=sys.stderr)
        return 130
    print(f"Download failed: {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
