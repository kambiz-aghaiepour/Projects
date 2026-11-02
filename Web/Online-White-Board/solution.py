#!/usr/bin/env python3
"""Online White Board - a small collaborative drawing board.

A standard-library HTTP server stores boards and strokes in SQLite and serves a
single-page HTML5 canvas client.  Clients draw with a pen or eraser, pick
colours and brush sizes, save a board as PNG, and poll the JSON API for strokes
added by other users.  ``--demo`` starts the server on an ephemeral loopback
port and exercises the API with urllib, so no browser or network is needed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

LOCALHOST = "127.0.0.1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 1_000_000
BOARD_PATH = re.compile(r"^/api/boards/([A-Za-z0-9_-]+)$")
STROKES_PATH = re.compile(r"^/api/boards/([A-Za-z0-9_-]+)/strokes$")
CLEAR_PATH = re.compile(r"^/api/boards/([A-Za-z0-9_-]+)/clear$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ApiError(Exception):
    """A client error that should be returned as a JSON response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def normalize_stroke(raw: Any) -> dict[str, Any]:
    """Validate and compact one stroke received from a client."""
    if not isinstance(raw, dict):
        raise ApiError(400, "each stroke must be an object")
    tool = raw.get("tool", "pen")
    if tool not in ("pen", "eraser"):
        raise ApiError(400, "tool must be 'pen' or 'eraser'")
    color = raw.get("color", "#1f2937")
    if not isinstance(color, str) or not COLOR_RE.match(color):
        raise ApiError(400, "color must be a #rrggbb string")
    try:
        size = float(raw.get("size", 3))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "size must be a number") from exc
    if not math.isfinite(size) or not 1 <= size <= 64:
        raise ApiError(400, "size must be between 1 and 64")
    points = raw.get("points")
    if not isinstance(points, list) or not points:
        raise ApiError(400, "points must be a non-empty list")
    if len(points) > 5000:
        raise ApiError(400, "a stroke may contain at most 5000 points")
    clean_points: list[list[float]] = []
    for point in points:
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)):
            raise ApiError(400, "each point must be [x, y] numbers")
        clean_points.append([round(float(point[0]), 2), round(float(point[1]), 2)])
    return {"tool": tool, "color": color.upper(), "size": round(size, 2),
            "points": clean_points}


class BoardStore:
    """SQLite persistence for boards and their strokes."""

    def __init__(self, path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS boards (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strokes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                data TEXT NOT NULL,
                created REAL NOT NULL,
                UNIQUE (board_id, seq)
            );
            CREATE INDEX IF NOT EXISTS strokes_board_seq ON strokes(board_id, seq);
            """
        )
        self._conn.commit()

    def create_board(self, name: str) -> dict[str, Any]:
        """Create a board and return its public representation."""
        name = " ".join(name.split())[:80] or "Untitled board"
        board_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO boards (id, name, created) VALUES (?, ?, ?)",
                               (board_id, name, now))
        return {"id": board_id, "name": name, "created": now, "stroke_count": 0,
                "updated": now}

    def list_boards(self) -> list[dict[str, Any]]:
        """Return boards, most recently updated first."""
        rows = self._conn.execute(
            """
            SELECT b.id, b.name, b.created, COUNT(s.id) AS stroke_count,
                   COALESCE(MAX(s.created), b.created) AS updated
            FROM boards b LEFT JOIN strokes s ON s.board_id = b.id
            GROUP BY b.id ORDER BY updated DESC, b.name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def board_exists(self, board_id: str) -> bool:
        """Return whether ``board_id`` is known."""
        row = self._conn.execute("SELECT 1 FROM boards WHERE id = ?", (board_id,)).fetchone()
        return row is not None

    def get_board(self, board_id: str) -> dict[str, Any]:
        """Return a board with every stroke."""
        row = self._conn.execute("SELECT id, name, created FROM boards WHERE id = ?",
                                 (board_id,)).fetchone()
        if row is None:
            raise ApiError(404, "board not found")
        strokes = self.strokes_since(board_id, 0)["strokes"]
        return {"id": row["id"], "name": row["name"], "created": row["created"],
                "strokes": strokes, "last_seq": strokes[-1]["seq"] if strokes else 0}

    def strokes_since(self, board_id: str, since: int) -> dict[str, Any]:
        """Return strokes with ``seq > since`` plus the newest sequence number."""
        if not self.board_exists(board_id):
            raise ApiError(404, "board not found")
        rows = self._conn.execute(
            "SELECT seq, data FROM strokes WHERE board_id = ? AND seq > ? ORDER BY seq",
            (board_id, since),
        ).fetchall()
        strokes = []
        for row in rows:
            stroke = json.loads(row["data"])
            stroke["seq"] = row["seq"]
            strokes.append(stroke)
        last = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM strokes "
                                  "WHERE board_id = ?", (board_id,)).fetchone()["seq"]
        return {"strokes": strokes, "last_seq": int(last)}

    def add_strokes(self, board_id: str, raw_strokes: list[Any]) -> dict[str, Any]:
        """Append validated strokes atomically and return their sequence numbers."""
        if not raw_strokes:
            raise ApiError(400, "strokes must be a non-empty list")
        if len(raw_strokes) > 500:
            raise ApiError(400, "at most 500 strokes per request")
        strokes = [normalize_stroke(raw) for raw in raw_strokes]
        if not self.board_exists(board_id):
            raise ApiError(404, "board not found")
        with self._lock, self._conn:
            start = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM strokes WHERE board_id = ?",
                (board_id,)).fetchone()[0]
            now = time.time()
            for offset, stroke in enumerate(strokes, start=1):
                self._conn.execute(
                    "INSERT INTO strokes (board_id, seq, data, created) VALUES (?, ?, ?, ?)",
                    (board_id, start + offset, json.dumps(stroke, separators=(",", ":")), now),
                )
        assigned = list(range(start + 1, start + 1 + len(strokes)))
        return {"assigned": assigned, "last_seq": assigned[-1] if assigned else start}

    def clear_board(self, board_id: str) -> None:
        """Delete every stroke from a board."""
        if not self.board_exists(board_id):
            raise ApiError(404, "board not found")
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM strokes WHERE board_id = ?", (board_id,))

    def delete_board(self, board_id: str) -> None:
        """Delete a board and its strokes."""
        if not self.board_exists(board_id):
            raise ApiError(404, "board not found")
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()


class BoardHandler(BaseHTTPRequestHandler):
    """JSON API plus the single-page canvas client."""

    store: BoardStore
    server_version = "WhiteBoard/1.0"

    def log_message(self, format: str, *args: object) -> None:
        """Suppress per-request logging; the API is polled frequently."""

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(404, {"error": "file not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "invalid Content-Length") from exc
        if length <= 0:
            raise ApiError(400, "JSON body required")
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, "invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "JSON body must be an object")
        return payload

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if method == "GET" and path in ("/", "/index.html"):
                index = STATIC_DIR / "index.html"
                if not index.exists():
                    raise ApiError(500, "static/index.html is missing")
                self._send_file(index, "text/html; charset=utf-8")
                return
            if method == "GET" and path == "/api/boards":
                self._send_json(200, {"boards": self.store.list_boards()})
                return
            if method == "POST" and path == "/api/boards":
                payload = self._read_json()
                name = payload.get("name", "Untitled board")
                if not isinstance(name, str):
                    raise ApiError(400, "name must be a string")
                self._send_json(201, {"board": self.store.create_board(name)})
                return

            match = STROKES_PATH.match(path)
            if match and method in ("GET", "POST"):
                board_id = match.group(1)
                if method == "GET":
                    since = parse_qs(parsed.query).get("since", ["0"])[0]
                    try:
                        since_number = max(0, int(since))
                    except ValueError as exc:
                        raise ApiError(400, "since must be an integer") from exc
                    self._send_json(200, self.store.strokes_since(board_id, since_number))
                else:
                    payload = self._read_json()
                    strokes = payload.get("strokes")
                    if strokes is None and "points" in payload:
                        strokes = [payload]
                    if not isinstance(strokes, list):
                        raise ApiError(400, "strokes must be a list")
                    self._send_json(201, self.store.add_strokes(board_id, strokes))
                return

            match = CLEAR_PATH.match(path)
            if match and method == "POST":
                self.store.clear_board(match.group(1))
                self._send_json(200, {"cleared": True})
                return

            match = BOARD_PATH.match(path)
            if match and method == "GET":
                self._send_json(200, {"board": self.store.get_board(match.group(1))})
                return
            if match and method == "DELETE":
                self.store.delete_board(match.group(1))
                self._send_json(200, {"deleted": True})
                return

            raise ApiError(404, "not found")
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # keep the server alive on unexpected failures
            print(f"server error: {exc}", file=sys.stderr)
            self._send_json(500, {"error": "internal server error"})

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802 - http.server API
        self._dispatch("DELETE")


def make_server(host: str, port: int, db_path: str | Path) -> tuple[ThreadingHTTPServer, BoardStore]:
    """Create the HTTP server and its store, binding the requested address."""
    store = BoardStore(db_path)
    handler = type("BoundBoardHandler", (BoardHandler,), {"store": store})
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError:
        store.close()
        raise
    return server, store


def run_server(args: argparse.Namespace) -> int:
    """Run the board server until interrupted."""
    try:
        server, store = make_server(args.host, args.port, args.db)
    except OSError as exc:
        print(f"error: cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    host, port = server.server_address[:2]
    print(f"Online White Board running at http://{host}:{port}/  (database: {args.db})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.shutdown()
        server.server_close()
        store.close()
    return 0


# --------------------------------------------------------------------------- demo

def _demo_request(base: str, method: str, path: str,
                  payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """Call the local API and decode its JSON response."""
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def run_demo() -> int:
    """Start a throwaway server and exercise board and stroke CRUD over HTTP."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        server, store = make_server(LOCALHOST, 0, Path(tmp) / "demo.db")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://{LOCALHOST}:{server.server_address[1]}"
        print("Online White Board demo (offline: local server + disposable SQLite database)")
        print(f"Server: {base}\n")
        try:
            status, listing = _demo_request(base, "GET", "/api/boards")
            print(f"1. GET  /api/boards            -> {status}, {len(listing['boards'])} board(s)")
            status, created = _demo_request(base, "POST", "/api/boards",
                                            {"name": "  Demo brainstorm  "})
            board = created["board"]
            board_id = board["id"]
            print(f"2. POST /api/boards            -> {status}, id={board_id}, "
                  f"name={board['name']!r}")

            strokes = [
                {"tool": "pen", "color": "#e11d48", "size": 4,
                 "points": [[40, 60], [120, 110], [200, 70], [280, 130]]},
                {"tool": "pen", "color": "#2563eb", "size": 8,
                 "points": [[300, 200], [360, 250], [430, 210]]},
                {"tool": "eraser", "color": "#ffffff", "size": 12,
                 "points": [[100, 100], [140, 120]]},
            ]
            status, added = _demo_request(base, "POST", f"/api/boards/{board_id}/strokes",
                                          {"strokes": strokes})
            print(f"3. POST .../strokes            -> {status}, assigned seq={added['assigned']}")

            status, fetched = _demo_request(base, "GET", f"/api/boards/{board_id}")
            got = fetched["board"]
            print(f"4. GET  .../boards/{board_id} -> {status}, "
                  f"{len(got['strokes'])} strokes, last_seq={got['last_seq']}")

            status, delta = _demo_request(base, "GET", f"/api/boards/{board_id}/strokes?since=2")
            print(f"5. GET  .../strokes?since=2    -> {status}, "
                  f"{len(delta['strokes'])} new stroke(s), last_seq={delta['last_seq']}")

            status, added = _demo_request(base, "POST", f"/api/boards/{board_id}/strokes",
                                          {"strokes": [{"tool": "pen", "color": "#16a34a",
                                                        "size": 2,
                                                        "points": [[500, 300], [520, 320]]}]})
            print(f"6. POST one more stroke        -> {status}, seq={added['assigned']}")

            status, listing = _demo_request(base, "GET", "/api/boards")
            summary = listing["boards"][0]
            print(f"7. GET  /api/boards            -> {status}, {len(listing['boards'])} board, "
                  f"{summary['stroke_count']} strokes in {summary['name']!r}")
            print("   persistence check           -> "
                  f"{'OK' if store.strokes_since(board_id, 0)['last_seq'] == 4 else 'FAILED'}")

            status, cleared = _demo_request(base, "POST", f"/api/boards/{board_id}/clear")
            status2, empty = _demo_request(base, "GET", f"/api/boards/{board_id}")
            print(f"8. POST .../clear              -> {status}; "
                  f"{len(empty['board']['strokes'])} strokes remain")

            from urllib.request import urlopen
            with urlopen(base + "/", timeout=5) as response:
                html = response.read().decode("utf-8")
            print(f"9. GET  /                      -> {response.status}, "
                  f"{len(html)} bytes of HTML, canvas={'<canvas' in html}")

            ok = (added["assigned"] == [4] and summary["stroke_count"] == 4
                  and delta["last_seq"] == 3 and cleared.get("cleared") is True)
            print(f"\nDemo complete: API round trip "
                  f"{'passed' if ok else 'FAILED'}; board data persisted in SQLite.")
            return 0 if ok else 1
        finally:
            server.shutdown()
            server.server_close()
            store.close()


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Run a collaborative HTML5 white board backed by SQLite.",
        epilog="Examples:\n"
               "  python3 solution.py --port 8000\n"
               "  python3 solution.py --db boards.db --port 0\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=LOCALHOST,
                        help=f"bind address (default: {LOCALHOST})")
    parser.add_argument("--port", type=int, default=8000,
                        help="port to listen on; 0 picks a free port (default: 8000)")
    parser.add_argument("--db", default="whiteboard.db",
                        help="SQLite database path (default: whiteboard.db)")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline API demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if not STATIC_DIR.is_dir():
        print(f"error: static assets missing at {STATIC_DIR}", file=sys.stderr)
        return 1
    return run_server(args)


if __name__ == "__main__":
    raise SystemExit(main())
