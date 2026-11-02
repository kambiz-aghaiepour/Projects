"""Throttled loopback HTTP server used by ``solution.py --demo``.

It serves one in-memory payload and implements single-range ``Range``
requests, which lets the demo exercise resume support without any network
access.  A configurable per-chunk delay makes the progress bar observable.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

BLOCK_SIZE = 64 * 1024


class _DemoHandler(BaseHTTPRequestHandler):
    """Serve one in-memory payload, honouring a single ``bytes=`` range."""

    payload: bytes = b""
    delay: float = 0.0
    server_version = "ProgressDemo/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] not in ("/", "/sample.bin"):
            self.send_error(404, "not found")
            return

        length = len(self.payload)
        start, end = 0, length - 1
        status = 200
        header = self.headers.get("Range", "")
        if header.startswith("bytes="):
            spec = header[6:].split(",", 1)[0].strip()
            first, _, last = spec.partition("-")
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else length - 1
                else:
                    start = max(0, length - int(last))
                    end = length - 1
            except ValueError:
                self.send_error(400, "malformed range")
                return
            if start >= length or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{length}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206

        body_length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(body_length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{length}")
        self.end_headers()

        position = start
        try:
            while position <= end:
                block = self.payload[position : min(position + BLOCK_SIZE, end + 1)]
                self.wfile.write(block)
                self.wfile.flush()
                position += len(block)
                if self.delay:
                    time.sleep(self.delay)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client aborted on purpose during the resume demo

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def demo_server(payload: bytes, delay: float = 0.02) -> Iterator[str]:
    """Start a throttled loopback server and yield its payload URL."""
    handler = type("DemoHandler", (_DemoHandler,), {"payload": payload, "delay": delay})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, name="demo-http", daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/sample.bin"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def build_payload(size: int) -> bytes:
    """Build a deterministic test payload of exactly ``size`` bytes."""
    block = bytes(range(256)) * 256  # 64 KiB
    return (block * (size // len(block) + 1))[:size]
