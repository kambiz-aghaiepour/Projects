#!/usr/bin/env python3
"""A small video streaming server and HTML5 player.

Serves a local video file over HTTP with proper ``Range`` support (``206
Partial Content``, suffix ranges and ``416`` for unsatisfiable requests) so a
browser can start playback before the whole file is downloaded and can seek
freely.  The player page is generated on the fly and uses the native HTML5
``<video>`` element plus a live stream-diagnostics panel.

Only the Python standard library is required for serving; ``ffmpeg`` is used by
the demo to synthesise a tiny test clip when it is installed.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import http.client
import http.server
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Iterator

CHUNK_SIZE = 64 * 1024
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".ogg": "video/ogg",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiable(ValueError):
    """The requested byte range lies outside the file."""


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Parse a single ``Range`` header into inclusive ``(start, end)``.

    Returns ``None`` when the header is absent.  Raises
    :class:`RangeNotSatisfiable` for malformed or out-of-bounds ranges.
    """
    if not header:
        return None
    match = RANGE_RE.match(header.strip())
    if not match:
        raise RangeNotSatisfiable("only a single byte range is supported")
    first, last = match.groups()
    if not first and not last:
        raise RangeNotSatisfiable("empty range")
    if not first:  # bytes=-N : final N bytes
        suffix = int(last)
        if suffix <= 0:
            raise RangeNotSatisfiable("zero-length suffix")
        return max(0, size - suffix), size - 1
    start = int(first)
    if start >= size:
        raise RangeNotSatisfiable("start beyond end of file")
    end = int(last) if last else size - 1
    end = min(end, size - 1)
    if end < start:
        raise RangeNotSatisfiable("end before start")
    return start, end


def guess_content_type(path: Path) -> str:
    """Return a video MIME type for ``path`` (falling back to octet-stream)."""
    suffix = path.suffix.lower()
    if suffix in VIDEO_TYPES:
        return VIDEO_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


@dataclass
class StreamServer:
    """Handle for a running :class:`ThreadingHTTPServer`."""

    httpd: http.server.ThreadingHTTPServer
    thread: threading.Thread
    video: Path

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.httpd.server_address[0]}:{self.port}"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class StreamHandler(http.server.BaseHTTPRequestHandler):
    """Serve the player page and one video file with byte-range support."""

    protocol_version = "HTTP/1.1"
    server_version = "MiniStream/1.0"

    @property
    def video_path(self) -> Path:
        return self.server.video_path  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "verbose", False):  # type: ignore[attr-defined]
            range_header = self.headers.get("Range")
            suffix = f" Range={range_header}" if range_header else ""
            sys.stderr.write(f"[stream] {self.address_string()} {format % args}{suffix}\n")

    # -- helpers ---------------------------------------------------------
    def _send_body(self, body: bytes, status: int, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error_page(self, status: int, message: str) -> None:
        body = f"<!doctype html><title>{status}</title><h1>{status}</h1><p>{message}</p>".encode()
        self._send_body(body, status, "text/html; charset=utf-8")

    def _serve_video(self) -> None:
        path = self.video_path
        try:
            size = path.stat().st_size
        except OSError:
            self._send_error_page(404, "video file is no longer available")
            return
        if size == 0:
            self._send_error_page(416, "video file is empty")
            return

        content_type = guess_content_type(path)
        try:
            byte_range = parse_range(self.headers.get("Range", ""), size)
        except RangeNotSatisfiable as exc:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if getattr(self.server, "verbose", False):  # type: ignore[attr-defined]
                sys.stderr.write(f"[stream] 416 {exc}\n")
            return

        if byte_range is None:
            start, end, status = 0, size - 1, 200
        else:
            start, end = byte_range
            status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Last-Modified", time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(path.stat().st_mtime)))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        if self.command == "HEAD":
            return
        remaining = length
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                while remaining > 0:
                    chunk = handle.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers abandon requests when the user seeks; that is normal.
            self.close_connection = True

    # -- routes ----------------------------------------------------------
    def do_HEAD(self) -> None:  # noqa: N802 - http.server API
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        if route in ("/", "/index.html"):
            body = build_player_page(self.video_path.name, self.video_path.stat().st_size).encode("utf-8")
            self._send_body(body, 200, "text/html; charset=utf-8")
        elif route == "/health":
            body = json.dumps({"status": "ok", "video": self.video_path.name}).encode()
            self._send_body(body, 200, "application/json")
        elif route == "/media" or route.startswith("/media/"):
            self._serve_video()
        else:
            self._send_error_page(404, "not found")

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server API
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()


def build_player_page(filename: str, size: int) -> str:
    """Render the self-contained HTML5 player page."""
    template = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiniStream &middot; $filename</title>
<style>
  :root { color-scheme: dark; --accent: #6ee7b7; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #08080c;
         color: #ececf1; font: 15px/1.55 "Segoe UI", system-ui, sans-serif; }
  main { width: min(100vw, 980px); padding: 20px; }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 12px; letter-spacing: .02em; }
  h1 span { color: #8b8b9a; font-weight: 400; }
  .stage { position: relative; background: #000; border-radius: 14px; overflow: hidden;
           box-shadow: 0 26px 80px rgba(0,0,0,.65); }
  video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #000; }
  .panel { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 14px; }
  .stat { background: #111118; border: 1px solid #23232e; border-radius: 10px; padding: 9px 12px; }
  .stat b { display: block; color: #8b8b9a; font-size: 11px; font-weight: 600;
            letter-spacing: .09em; text-transform: uppercase; margin-bottom: 2px; }
  .stat code { font: 13px/1.4 ui-monospace, Menlo, Consolas, monospace; color: var(--accent); }
  .bar { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button { appearance: none; border: 1px solid #2c2c38; background: #15151d; color: inherit;
           padding: 8px 12px; border-radius: 9px; font: inherit; cursor: pointer; }
  button:hover { border-color: var(--accent); color: var(--accent); }
  .note { color: #7c7c8c; font-size: 12.5px; margin-top: 12px; }
</style>
</head>
<body>
<main>
  <h1>$filename <span>&middot; $size_mib MiB served with HTTP range requests</span></h1>
  <div class="stage">
    <video id="player" controls preload="metadata" playsinline
           src="/media/$quoted_name"></video>
  </div>
  <div class="panel">
    <div class="stat"><b>Status</b><code id="status">loading</code></div>
    <div class="stat"><b>Duration</b><code id="duration">&mdash;</code></div>
    <div class="stat"><b>Position</b><code id="position">0.00 s</code></div>
    <div class="stat"><b>Buffered</b><code id="buffered">&mdash;</code></div>
    <div class="stat"><b>Range probe</b><code id="probe">pending</code></div>
    <div class="stat"><b>Ready state</b><code id="ready">0</code></div>
  </div>
  <div class="bar">
    <button data-seek="0.25">Seek 25%</button>
    <button data-seek="0.5">Seek 50%</button>
    <button data-seek="0.75">Seek 75%</button>
    <button id="restart">Restart</button>
  </div>
  <p class="note">Seeking jumps to a byte offset: the server answers with <code>206 Partial Content</code>
  and a <code>Content-Range</code> header, so only the bytes needed are transferred.</p>
</main>
<script>
const video = document.getElementById('player');
const byId = (id) => document.getElementById(id);
const fmt = (seconds) => Number.isFinite(seconds) ? seconds.toFixed(2) + ' s' : '\\u2014';

function refresh() {
  byId('position').textContent = fmt(video.currentTime);
  byId('duration').textContent = fmt(video.duration);
  byId('ready').textContent = String(video.readyState);
  if (video.buffered.length) {
    const ranges = [];
    for (let i = 0; i < video.buffered.length; i++) {
      ranges.push(fmt(video.buffered.start(i)) + '\\u2013' + fmt(video.buffered.end(i)));
    }
    byId('buffered').textContent = ranges.join(', ');
  }
}

video.addEventListener('loadedmetadata', refresh);
video.addEventListener('canplay', () => {
  if (video.paused) byId('status').textContent = 'ready';
});
video.addEventListener('timeupdate', refresh);
video.addEventListener('progress', refresh);
video.addEventListener('waiting', () => byId('status').textContent = 'buffering');
video.addEventListener('playing', () => byId('status').textContent = 'playing');
video.addEventListener('pause', () => byId('status').textContent = 'paused');
video.addEventListener('error', () => byId('status').textContent = 'error');

document.querySelectorAll('[data-seek]').forEach((button) => {
  button.addEventListener('click', () => {
    if (Number.isFinite(video.duration)) {
      video.currentTime = video.duration * parseFloat(button.dataset.seek);
      video.play().catch(() => {});
    }
  });
});
document.getElementById('restart').addEventListener('click', () => {
  video.currentTime = 0;
  video.play().catch(() => {});
});

// Prove to the user that byte ranges work, independently of the video element.
fetch('/media/$quoted_name', { headers: { Range: 'bytes=0-1023' } })
  .then((response) => response.headers.get('Content-Range') || ('HTTP ' + response.status))
  .then((text) => { byId('probe').textContent = text; })
  .catch(() => { byId('probe').textContent = 'unavailable'; });
refresh();
</script>
</body>
</html>
""")
    return template.substitute(
        filename=html.escape(filename),
        quoted_name=urllib.parse.quote(filename),
        size_mib=f"{size / (1024 * 1024):.2f}",
    )


@contextlib.contextmanager
def running_server(video: Path, host: str = "127.0.0.1", port: int = 0, verbose: bool = False) -> Iterator[StreamServer]:
    """Start the streaming server on a background thread and stop it on exit."""
    handler = StreamHandler
    httpd = http.server.ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    httpd.video_path = video  # type: ignore[attr-defined]
    httpd.verbose = verbose  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, name="stream-server", daemon=True)
    thread.start()
    server = StreamServer(httpd, thread, video)
    try:
        yield server
    finally:
        server.stop()


def make_demo_video(destination: Path) -> bool:
    """Create a 3 second test clip with ffmpeg; return False when unavailable."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and destination.exists() and destination.stat().st_size > 0


def make_fallback_video(destination: Path) -> int:
    """Write a minimal MP4-like file so demo verification can run offline."""
    header = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 4000
    destination.write_bytes(header)
    return len(header)


def probe(server: StreamServer, filename: str) -> list[tuple[str, str, bool]]:
    """Issue HTTP requests against a running server and check the responses."""
    results: list[tuple[str, str, bool]] = []
    host, port = server.httpd.server_address[:2]
    media = "/media/" + urllib.parse.quote(filename)

    def request(method: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        info = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, info, body

    size = Path(server.video).stat().st_size
    status, headers, body = request("GET", "/")
    ok = status == 200 and "text/html" in headers.get("content-type", "") and b"<video" in body
    results.append(("player page", f"HTTP {status}, {len(body)} bytes", ok))

    status, headers, _ = request("HEAD", media)
    ok = status == 200 and int(headers.get("content-length", -1)) == size and headers.get("accept-ranges") == "bytes"
    results.append(("HEAD media", f"HTTP {status}, length={headers.get('content-length')}, accept-ranges={headers.get('accept-ranges')}", ok))

    status, headers, body = request("GET", media, {"Range": "bytes=0-99"})
    content_range = headers.get("content-range", "")
    ok = status == 206 and len(body) == 100 and content_range == f"bytes 0-99/{size}"
    results.append(("range 0-99", f"HTTP {status}, {len(body)} bytes, Content-Range: {content_range}", ok))

    start = max(0, size // 2)
    status, headers, body = request("GET", media, {"Range": f"bytes={start}-"})
    ok = status == 206 and len(body) == size - start and headers.get("content-range") == f"bytes {start}-{size - 1}/{size}"
    results.append((f"range {start}-", f"HTTP {status}, {len(body)} bytes", ok))

    status, headers, body = request("GET", media, {"Range": "bytes=-64"})
    ok = status == 206 and len(body) == 64 and headers.get("content-range") == f"bytes {size - 64}-{size - 1}/{size}"
    results.append(("suffix range -64", f"HTTP {status}, {len(body)} bytes", ok))

    status, headers, body = request("GET", media, {"Range": f"bytes={size + 10}-"})
    content_range = headers.get("content-range", "")
    ok = status == 416 and content_range == f"bytes */{size}" and not body
    results.append(("out-of-range", f"HTTP {status}, Content-Range: {content_range}", ok))

    status, headers, body = request("GET", media)
    ok = status == 200 and len(body) == size and headers.get("content-type", "").startswith("video/")
    results.append(("full download", f"HTTP {status}, {len(body)} bytes, {headers.get('content-type')}", ok))
    return results


def run_demo() -> int:
    """Create a video, start the server on an ephemeral port and probe it."""
    workdir = Path(tempfile.mkdtemp(prefix="stream-video-demo-"))
    video = workdir / "sample.mp4"
    print("Stream Video from Online demo")
    print(f"  workspace: {workdir}")

    if make_demo_video(video):
        print(f"  video    : sample.mp4 ({video.stat().st_size / 1024:.1f} KiB, generated with ffmpeg)")
    else:
        size = make_fallback_video(video)
        print(f"  video    : sample.mp4 ({size} bytes, fallback header; ffmpeg not available)")

    with running_server(video, host="127.0.0.1", port=0) as server:
        print(f"  server   : {server.base_url}  (ephemeral port, background thread)")
        results = probe(server, video.name)
        print("  range probes:")
        for label, detail, ok in results:
            print(f"    [{'PASS' if ok else 'FAIL'}] {label:<16} {detail}")
    print(f"  result   : {sum(1 for _, _, ok in results if ok)}/{len(results)} checks passed")
    print("Demo complete: run without --demo to serve your own video and open the player in a browser.")
    return 0 if all(ok for _, _, ok in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve a video over HTTP with byte-range seeking and an HTML5 player.",
        epilog="Example: python3 solution.py movie.mp4 --port 8000",
    )
    parser.add_argument("video", nargs="?", metavar="FILE", help="video file to stream")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1; use 0.0.0.0 to share)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000; 0 picks a free port)")
    parser.add_argument("--open", action="store_true", help="open the player page in a browser")
    parser.add_argument("--verbose", action="store_true", help="log every request, including Range headers")
    parser.add_argument("--demo", action="store_true", help="generate a test clip and verify range responses")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.video:
        if not sys.stdin.isatty():
            parser.error("no video file given (try --demo)")
        try:
            raw = input("Video file to stream: ").strip().strip("'\"")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if not raw:
            parser.error("no video file given")
        args.video = raw

    video = Path(args.video).expanduser()
    if not video.is_file():
        print(f"Error: no such video file: {video}", file=sys.stderr)
        return 2
    if video.stat().st_size == 0:
        print(f"Error: video file is empty: {video}", file=sys.stderr)
        return 2

    try:
        with running_server(video, args.host, args.port, args.verbose) as server:
            print(f"Streaming {video.name} ({video.stat().st_size / 1024:.1f} KiB)")
            print(f"Player: {server.base_url}/")
            print("Press Ctrl+C to stop.")
            if args.open:
                webbrowser.open(server.base_url + "/")
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except OSError as exc:
        print(f"Error: cannot start server on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
