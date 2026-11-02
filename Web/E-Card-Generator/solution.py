#!/usr/bin/env python3
"""E-Card Generator: a tiny site for creating and sharing picture e-cards.

Cards are rendered server-side with Pillow: a themed gradient background,
decorative motifs, a wrapped personal message and the recipient/sender names.
Records live in SQLite and the PNGs are written to a cards directory.  The
built-in HTTP server exposes a creation form, an HTML card page, the image
itself and a gallery.

``--demo`` renders a card offline, verifies the PNG, then starts an ephemeral
server and walks through creating, viewing and listing cards over HTTP.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import random
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

CARD_SIZE = (960, 640)
MAX_MESSAGE = 600

THEMES: dict[str, dict[str, object]] = {
    "sunset": {"top": (255, 154, 118), "bottom": (120, 40, 90), "ink": (255, 250, 240), "accent": (255, 214, 165), "motif": "hearts"},
    "ocean": {"top": (32, 120, 160), "bottom": (8, 34, 66), "ink": (240, 250, 255), "accent": (150, 230, 235), "motif": "bubbles"},
    "forest": {"top": (58, 110, 70), "bottom": (14, 38, 28), "ink": (244, 250, 235), "accent": (190, 225, 140), "motif": "leaves"},
    "night": {"top": (28, 36, 78), "bottom": (6, 8, 24), "ink": (238, 240, 255), "accent": (250, 220, 130), "motif": "stars"},
    "candy": {"top": (245, 160, 200), "bottom": (150, 90, 180), "ink": (255, 253, 250), "accent": (255, 235, 170), "motif": "confetti"},
    "paper": {"top": (248, 240, 225), "bottom": (222, 205, 180), "ink": (60, 48, 38), "accent": (150, 90, 60), "motif": "lines"},
}

QUOTES = [
    "Small joys are still joys.",
    "The best time to send a kind word is now.",
    "Friendship is a garden that needs watering.",
    "Somewhere, someone is smiling because of you.",
    "May your day be gentle and your coffee strong.",
    "Distance means little when the heart is close.",
]

_FONT_CANDIDATES = {
    "serif": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "C:/Windows/Fonts/georgia.ttf",
    ],
    "sans": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "sans-bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}


def load_font(style: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bundled/system font, falling back to Pillow's bitmap default."""
    for candidate in _FONT_CANDIDATES.get(style, []):
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


@dataclass(frozen=True)
class Card:
    """A rendered e-card."""

    card_id: str
    recipient: str
    sender: str
    message: str
    theme: str


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = CARD_SIZE
    image = Image.new("RGB", CARD_SIZE, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        draw.line([(0, y), (width, y)], fill=_lerp(top, bottom, y / (height - 1)))
    return image


def _heart(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill: tuple[int, int, int, int]) -> None:
    r = size / 4
    draw.ellipse([x - r * 2, y - r * 2, x, y], fill=fill)
    draw.ellipse([x, y - r * 2, x + r * 2, y], fill=fill)
    draw.polygon([(x - r * 2, y - r * 0.4), (x + r * 2, y - r * 0.4), (x, y + r * 2.2)], fill=fill)


def _star(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill: tuple[int, int, int, int]) -> None:
    draw.polygon([(x, y - size), (x + size * 0.25, y - size * 0.25), (x + size, y), (x + size * 0.25, y + size * 0.25),
                  (x, y + size), (x - size * 0.25, y + size * 0.25), (x - size, y), (x - size * 0.25, y - size * 0.25)], fill=fill)


def draw_motifs(image: Image.Image, theme: dict[str, object], seed: str) -> None:
    """Scatter theme-specific decorations around the card edges."""
    rng = random.Random(seed)
    accent = tuple(theme["accent"])  # type: ignore[arg-type]
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width, height = image.size
    for _ in range(34):
        x = rng.uniform(0, width)
        y = rng.uniform(0, height)
        # Keep the middle band clear for text.
        if 140 < y < height - 120:
            edge = min(x, width - x) < 150 or y < 130 or y > height - 110
            if not edge:
                continue
        size = rng.uniform(7, 22)
        alpha = rng.randint(45, 130)
        color = (*accent, alpha)
        motif = theme["motif"]
        if motif == "hearts":
            _heart(draw, x, y, size, color)
        elif motif == "bubbles":
            draw.ellipse([x - size, y - size, x + size, y + size], outline=color, width=2)
        elif motif == "leaves":
            draw.ellipse([x - size, y - size * 0.45, x + size, y + size * 0.45], outline=color, width=2)
        elif motif == "stars":
            _star(draw, x, y, size, color)
        elif motif == "confetti":
            draw.rectangle([x, y, x + size, y + size * 0.4], fill=color)
        else:
            draw.line([(x - size, y), (x + size, y)], fill=color, width=2)
    image.paste(layer, (0, 0), layer)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    """Greedy word wrap that also respects explicit newlines."""
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_card(card: Card, out_path: Path, seed: str | None = None) -> Path:
    """Render ``card`` to a PNG at ``out_path`` and return the path."""
    theme = THEMES[card.theme]
    top = tuple(theme["top"])  # type: ignore[arg-type]
    bottom = tuple(theme["bottom"])  # type: ignore[arg-type]
    image = _gradient(top, bottom)  # type: ignore[arg-type]
    draw = ImageDraw.Draw(image)
    accent = tuple(theme["accent"])  # type: ignore[arg-type]
    ink = tuple(theme["ink"])  # type: ignore[arg-type]

    # Soft inner panel + double border.
    panel = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle([36, 36, CARD_SIZE[0] - 36, CARD_SIZE[1] - 36], radius=22,
                            fill=(0, 0, 0, 38), outline=(*accent, 190), width=3)
    pdraw.rounded_rectangle([48, 48, CARD_SIZE[0] - 48, CARD_SIZE[1] - 48], radius=16,
                            outline=(*ink, 70), width=1)
    image.paste(panel, (0, 0), panel)

    draw_motifs(image, theme, seed or card.card_id)
    draw = ImageDraw.Draw(image)

    to_font = load_font("sans", 34)
    msg_size = 44 if len(card.message) <= 180 else 36
    msg_font = load_font("serif", msg_size)
    from_font = load_font("sans-bold", 30)
    draw.text((84, 86), "TO", font=load_font("sans-bold", 20), fill=_lerp(ink, accent, 0.35))
    draw.text((84, 116), card.recipient, font=to_font, fill=ink)

    lines = wrap_text(draw, card.message, msg_font, CARD_SIZE[0] - 200)
    while len(lines) > 10 and msg_size > 22:
        msg_size -= 3
        msg_font = load_font("serif", msg_size)
        lines = wrap_text(draw, card.message, msg_font, CARD_SIZE[0] - 200)
    line_height = int(msg_size * 1.42)
    total = len(lines) * line_height
    y = min(max(190, (CARD_SIZE[1] - total) // 2 + 10), 505 - total)
    y = max(150, y)
    for line in lines:
        draw.text((CARD_SIZE[0] // 2, y), line, font=msg_font, fill=ink, anchor="ma")
        y += line_height

    draw.text((84, CARD_SIZE[1] - 112), "—", font=from_font, fill=accent)
    draw.text((120, CARD_SIZE[1] - 112), card.sender, font=from_font, fill=ink)
    draw.text((CARD_SIZE[0] - 84, CARD_SIZE[1] - 70), "e-card generator", font=load_font("sans", 16),
              fill=_lerp(ink, bottom, 0.45), anchor="ra")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG")
    return out_path


class CardStore:
    """SQLite-backed card metadata store."""

    def __init__(self, db_path: Path, cards_dir: Path) -> None:
        self.db_path = db_path
        self.cards_dir = cards_dir
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, recipient TEXT NOT NULL, "
            "sender TEXT NOT NULL, message TEXT NOT NULL, theme TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        self.conn.commit()

    def create(self, recipient: str, sender: str, message: str, theme: str) -> Card:
        if theme not in THEMES:
            raise ValueError(f"unknown theme: {theme!r}")
        recipient = recipient.strip()[:80]
        sender = (sender.strip() or "Anonymous")[:80]
        message = message.strip()
        if not recipient:
            raise ValueError("recipient is required")
        if not message:
            raise ValueError("message is required")
        if len(message) > MAX_MESSAGE:
            raise ValueError(f"message is longer than {MAX_MESSAGE} characters")
        with self._lock:
            for _ in range(10):
                card_id = secrets.token_hex(4)
                if self.conn.execute("SELECT 1 FROM cards WHERE id = ?", (card_id,)).fetchone() is None:
                    break
            else:
                raise RuntimeError("could not allocate a unique card id")
            card = Card(card_id, recipient, sender, message, theme)
            render_card(card, self.cards_dir / f"{card_id}.png")
            self.conn.execute(
                "INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?)",
                (card_id, recipient, sender, message, theme, time.time()),
            )
            self.conn.commit()
            return card

    def get(self, card_id: str) -> Card | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            return None
        return Card(row["id"], row["recipient"], row["sender"], row["message"], row["theme"])

    def recent(self, limit: int = 24) -> list[Card]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM cards ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [Card(r["id"], r["recipient"], r["sender"], r["message"], r["theme"]) for r in rows]

    def close(self) -> None:
        self.conn.close()


def page(title: str, body: str) -> str:
    """Wrap page content in the shared site chrome."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin:0; font-family: Georgia, 'Times New Roman', serif; background:#141021; color:#f5efe6; }}
header {{ display:flex; justify-content:space-between; align-items:center; padding:18px 28px;
  border-bottom:1px solid #332a4a; background:#191329; }}
header a {{ color:#ffd9a0; text-decoration:none; margin-left:18px; font-family:system-ui,sans-serif; }}
h1 {{ font-size:2rem; margin:0 0 6px; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:32px 24px 64px; }}
.lead {{ color:#c9bfd8; font-family:system-ui,sans-serif; }}
form.card-form {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; background:#1d1730;
  border:1px solid #332a4a; border-radius:14px; padding:26px; margin-top:24px; }}
label {{ font-family:system-ui,sans-serif; font-size:.82rem; letter-spacing:.06em; text-transform:uppercase; color:#b9a9d0; }}
input,select,textarea {{ width:100%; box-sizing:border-box; margin-top:7px; padding:11px 12px; border-radius:8px;
  border:1px solid #463a63; background:#141021; color:#f5efe6; font:inherit; }}
textarea {{ min-height:150px; resize:vertical; }}
.full {{ grid-column:1 / -1; }}
button {{ cursor:pointer; border:0; border-radius:999px; padding:12px 26px; font:600 1rem system-ui,sans-serif;
  background:linear-gradient(90deg,#ffb26b,#ff7e9d); color:#241326; }}
button:hover {{ filter:brightness(1.08); }}
.actions {{ grid-column:1 / -1; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }}
.hint {{ font-family:system-ui,sans-serif; font-size:.85rem; color:#a99cbd; }}
.card-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:20px; margin-top:26px; }}
.card-grid a {{ text-decoration:none; color:inherit; background:#1d1730; border:1px solid #332a4a;
  border-radius:12px; overflow:hidden; display:block; }}
.card-grid img {{ width:100%; display:block; aspect-ratio:3/2; object-fit:cover; }}
.card-grid span {{ display:block; padding:10px 12px; font-family:system-ui,sans-serif; font-size:.9rem; }}
.share {{ background:#1d1730; border:1px solid #332a4a; border-radius:14px; padding:22px; margin-top:22px; }}
.share code {{ background:#141021; padding:5px 9px; border-radius:6px; word-break:break-all; }}
.notice {{ background:#3a1f33; border:1px solid #7c3d5e; padding:12px 16px; border-radius:8px; font-family:system-ui,sans-serif; }}
</style></head>
<body>
<header><strong>✉ E-Card Generator</strong><nav><a href="/">Create</a><a href="/gallery">Gallery</a></nav></header>
<div class="wrap">{body}</div>
</body></html>"""


def card_page(card: Card) -> str:
    """HTML view of a single card."""
    theme = THEMES[card.theme]
    top, bottom = theme["top"], theme["bottom"]
    body = f"""
<h1>{html.escape(card.message[:60])}{'…' if len(card.message) > 60 else ''}</h1>
<p class="lead">A card for <strong>{html.escape(card.recipient)}</strong>, from {html.escape(card.sender)}.</p>
<div style="margin-top:24px;border-radius:16px;overflow:hidden;border:1px solid #463a63;
  background:linear-gradient(135deg,rgb{top},rgb{bottom});">
  <img src="/cards/{card.card_id}.png" alt="E-card for {html.escape(card.recipient)}" style="width:100%;display:block;">
</div>
<p style="margin-top:16px;font-family:system-ui,sans-serif;color:#c9bfd8;">
  Theme: {html.escape(card.theme)} · Card ID: <code>{card.card_id}</code></p>
<div class="share"><strong>Share this card</strong>
  <p><code>/card/{card.card_id}</code></p>
  <p class="hint">Anyone with the link can view it. <a href="/cards/{card.card_id}.png">Download the PNG</a>.</p>
</div>
<p style="margin-top:22px"><a href="/" style="color:#ffd9a0">← Create your own</a></p>
"""
    return page(f"Card for {card.recipient}", body)


def index_page(error: str = "", values: dict[str, str] | None = None) -> str:
    """Creation form."""
    values = values or {"theme": "sunset"}
    options = "".join(
        f'<option value="{name}"{" selected" if name == values.get("theme") else ""}>{name.title()}</option>'
        for name in THEMES
    )
    error_html = f'<p class="notice">{html.escape(error)}</p>' if error else ""
    quotes_js = ", ".join(json.dumps(q) for q in QUOTES)
    body = f"""
<h1>Send a little picture</h1>
<p class="lead">Pick a theme, write a note, and we will paint a postcard-sized e-card you can share as a link or PNG.</p>
{error_html}
<form class="card-form" method="post" action="/create">
  <div><label for="recipient">To</label>
    <input id="recipient" name="recipient" maxlength="80" required placeholder="Ada" value="{html.escape(values.get('recipient', ''))}"></div>
  <div><label for="sender">From</label>
    <input id="sender" name="sender" maxlength="80" placeholder="Your name" value="{html.escape(values.get('sender', ''))}"></div>
  <div class="full"><label for="message">Message</label>
    <textarea id="message" name="message" maxlength="{MAX_MESSAGE}" required placeholder="Thinking of you…">{html.escape(values.get('message', ''))}</textarea>
    <div class="hint"><span id="count">0</span> / {MAX_MESSAGE} characters</div></div>
  <div><label for="theme">Theme</label><select id="theme" name="theme">{options}</select></div>
  <div class="actions"><button type="submit">Create e-card</button>
    <button type="button" id="motto" style="background:#2a2140;color:#ffd9a0">Insert a motto</button>
    <span class="hint">Six hand-picked sentiments, no Flash required.</span></div>
</form>
<script>
const quotes = [{quotes_js}];
const box = document.getElementById('message');
const count = document.getElementById('count');
const update = () => count.textContent = box.value.length;
box.addEventListener('input', update); update();
document.getElementById('motto').addEventListener('click', () => {{
  box.value = quotes[Math.floor(Math.random() * quotes.length)];
  update(); box.focus();
}});
</script>
"""
    return page("E-Card Generator", body)


class Handler(BaseHTTPRequestHandler):
    """HTTP handler for the e-card site."""

    server_version = "ECardGenerator/1.0"

    @property
    def app(self) -> "App":
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        if self.app.verbose:
            super().log_message(format, *args)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, markup: str, extra: dict[str, str] | None = None) -> None:
        self._send(status, markup.encode("utf-8"), "text/html; charset=utf-8", extra)

    def _not_found(self, message: str = "Page not found") -> None:
        self._html(404, page("Not found", f"<h1>404</h1><p class='lead'>{html.escape(message)}</p>"
                                        "<p><a href='/' style='color:#ffd9a0'>Back to the generator</a></p>"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            self._html(200, index_page())
        elif path == "/gallery":
            cards = self.app.store.recent()
            if cards:
                cells = "".join(
                    f'<a href="/card/{c.card_id}"><img src="/cards/{c.card_id}.png" alt="Card for {html.escape(c.recipient)}">'
                    f"<span>To {html.escape(c.recipient)} · {html.escape(c.theme)}</span></a>"
                    for c in cards
                )
                body = (f"<h1>Gallery</h1><p class='lead'>{len(cards)} recent "
                        f"{'card' if len(cards) == 1 else 'cards'}.</p><div class='card-grid'>{cells}</div>")
            else:
                body = "<h1>Gallery</h1><p class='lead'>No cards yet. <a href='/' style='color:#ffd9a0'>Make the first one.</a></p>"
            self._html(200, page("Gallery", body))
        elif path == "/api/quote":
            self._send(200, json.dumps({"quote": random.choice(QUOTES)}).encode(), "application/json")
        elif path.startswith("/card/"):
            card = self.app.store.get(path.split("/", 2)[2])
            if card is None:
                self._not_found("That card does not exist.")
            else:
                self._html(200, card_page(card))
        elif path.startswith("/cards/") and path.endswith(".png"):
            card_id = path[len("/cards/"):-4]
            if not card_id.isalnum():
                self._not_found("Bad card id.")
                return
            image_path = self.app.store.cards_dir / f"{card_id}.png"
            if not image_path.is_file():
                self._not_found("That image does not exist.")
                return
            self._send(200, image_path.read_bytes(), "image/png", {"Cache-Control": "public, max-age=3600"})
        else:
            self._not_found()

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path != "/create":
            self._not_found()
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 64_000:
            self._html(400, index_page("Please fill in the form."))
            return
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
        try:
            card = self.app.store.create(
                form.get("recipient", ""), form.get("sender", ""), form.get("message", ""),
                form.get("theme", "sunset"),
            )
        except ValueError as exc:
            self._html(400, index_page(str(exc), form))
            return
        self.send_response(303)
        self.send_header("Location", f"/card/{card.card_id}")
        self.send_header("Content-Length", "0")
        self.end_headers()


class App:
    """Bundle of store plus server settings."""

    def __init__(self, db_path: Path, cards_dir: Path, verbose: bool = False) -> None:
        self.store = CardStore(db_path, cards_dir)
        self.verbose = verbose


def serve(app: App, port: int = 8000) -> None:
    """Run the site until interrupted."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]
    host, bound_port = server.server_address[:2]
    print(f"E-Card Generator running at http://{host}:{bound_port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.shutdown()
        server.server_close()


def _serve_background(app: App) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _http(url: str, data: dict[str, str] | None = None) -> tuple[int, bytes, str]:
    """GET/POST ``url`` and return status, body and final URL (errors included)."""
    payload = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(url, data=payload, timeout=10) as response:
            return response.status, response.read(), response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.url or url


def demo() -> int:
    """Offline + HTTP walkthrough that exercises every advertised feature."""
    print("E-Card Generator demo")
    print("=====================")
    checks: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory(prefix="ecards-") as tmp:
        root = Path(tmp)
        # 1. Pure offline render, no server involved.
        offline = Card("demo0001", "Ada Lovelace", "Charles Babbage",
                       "The Analytical Engine has no pretensions whatever to originate anything. "
                       "It can do whatever we know how to order it to perform.", "sunset")
        png = render_card(offline, root / "offline-card.png", seed="demo-motifs")
        with Image.open(png) as img:
            size_ok = img.size == CARD_SIZE
            colors = len(img.convert("RGB").getcolors(maxcolors=200_000) or [])
        bytes_ok = png.stat().st_size > 10_000
        checks.append(("offline render produced a PNG", png.is_file() and bytes_ok))
        checks.append((f"PNG dimensions are {CARD_SIZE[0]}x{CARD_SIZE[1]}", size_ok))
        checks.append((f"PNG has visual detail ({colors} colours)", colors > 500))
        print(f"  offline card : {png.name} ({png.stat().st_size:,} bytes, {colors:,} colours)")

        app = App(root / "ecards.db", root / "cards")
        server, base = _serve_background(app)
        try:
            status, body, _ = _http(f"{base}/")
            checks.append(("GET / serves the creation form", status == 200 and b"Create e-card" in body))

            status, body, final_url = _http(f"{base}/create", {
                "recipient": "Grace Hopper", "sender": "The Compiler Club",
                "message": "Thanks for debugging the impossible. Have a lovely week!",
                "theme": "ocean",
            })
            checks.append(("POST /create redirects to a card page", status == 200 and "/card/" in final_url))
            checks.append(("card page shows the recipient and message",
                           b"Grace Hopper" in body and b"debugging the impossible" in body))
            card_id = final_url.rsplit("/", 1)[-1]
            print(f"  http card id : {card_id}")

            status, image_bytes, _ = _http(f"{base}/cards/{card_id}.png")
            with Image.open(io.BytesIO(image_bytes)) as img:
                served_size = img.size
            checks.append(("served card image is a valid PNG", status == 200 and served_size == CARD_SIZE))
            checks.append(("card file exists on disk", (root / "cards" / f"{card_id}.png").is_file()))

            _http(f"{base}/create", {"recipient": "Alan Turing", "sender": "Bletchley",
                                     "message": "Tea is ready, and so is the machine.", "theme": "night"})
            status, gallery, _ = _http(f"{base}/gallery")
            checks.append(("gallery lists both cards", status == 200 and b"Grace Hopper" in gallery and b"Alan Turing" in gallery))

            status, quote_body, _ = _http(f"{base}/api/quote")
            checks.append(("motto API returns JSON", status == 200 and b'"quote"' in quote_body))

            status, bad_body, _ = _http(f"{base}/create", {"recipient": "", "message": "hi", "theme": "ocean"})
            checks.append(("invalid form returns 400 with an error", status == 400 and b"required" in bad_body))

            status, _, _ = _http(f"{base}/cards/does-not-exist.png")
            checks.append(("missing image returns 404", status == 404))
        finally:
            server.shutdown()
            server.server_close()
            app.store.close()
        print(f"  cards on disk: {len(list((root / 'cards').glob('*.png')))}")

    print()
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    failed = sum(1 for _, ok in checks if not ok)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Generate themed picture e-cards and serve a local sharing site.",
        epilog="Run with --demo for a scripted, offline walkthrough.",
    )
    parser.add_argument("--demo", action="store_true", help="render a card offline and exercise the site over HTTP")
    parser.add_argument("--serve", action="store_true", help="start the web server (default when no action is given)")
    parser.add_argument("--port", type=int, default=8000, help="port for --serve (default: 8000)")
    parser.add_argument("--db", type=Path, default=Path("e-cards.db"), help="SQLite database path")
    parser.add_argument("--cards-dir", type=Path, default=Path("cards"), help="directory for rendered PNGs")
    parser.add_argument("--render", type=Path, metavar="PNG", help="render a single card offline to this path")
    parser.add_argument("--to", default="Friend", help="recipient for --render")
    parser.add_argument("--from", dest="sender", default="Anonymous", help="sender for --render")
    parser.add_argument("--message", default="Thinking of you!", help="message for --render")
    parser.add_argument("--theme", choices=sorted(THEMES), default="sunset", help="colour theme")
    parser.add_argument("--seed", type=int, default=None, help="reserved for reproducible motif layouts")
    parser.add_argument("--list-themes", action="store_true", help="print the available themes and exit")
    parser.add_argument("--verbose", action="store_true", help="log HTTP requests")
    args = parser.parse_args(argv)

    if args.demo:
        return demo()
    if args.list_themes:
        for name, theme in THEMES.items():
            print(f"{name:8s} motif={theme['motif']}")
        return 0
    if args.render:
        card = Card(secrets.token_hex(4), args.to, args.sender, args.message, args.theme)
        path = render_card(card, args.render, seed=None if args.seed is None else f"seed-{args.seed}")
        print(f"Rendered {path} ({path.stat().st_size:,} bytes)")
        return 0
    if not (0 <= args.port <= 65535):
        parser.error("--port must be between 0 and 65535")
    app = App(args.db, args.cards_dir, verbose=args.verbose)
    try:
        serve(app, args.port)
    finally:
        app.store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
