#!/usr/bin/env python3
"""CAPTCHA Maker: distorted text challenges for signup forms.

Generates a five-character image with per-letter rotation, a sine-wave
displacement, coloured noise lines and speckles, plus an optional audio
challenge built from short tones.  Only a salted PBKDF2 hash of the answer is
stored, with an expiry time, attempt limit and one-time use.  Challenges are
served by a small HTTP API (``/api/challenge`` and ``/api/verify``) and can also
be created and checked from the command line.

``--demo`` renders several challenges and verifies correct, incorrect, reused
and expired answers, both directly and over HTTP.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import hmac
import html
import io
import json
import math
import os
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
import wave
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0 or 1
IMAGE_SIZE = (280, 100)
AUDIO_RATE = 22_050
DEFAULT_TTL = 300
DEFAULT_LENGTH = 5
DEFAULT_ATTEMPTS = 3
HASH_ROUNDS = 120_000

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Pick a bold system font, falling back to Pillow's default."""
    for path in _FONT_PATHS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _gradient_background(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    width, height = size
    base = [rng.randint(225, 250) for _ in range(3)]
    tint = [max(180, min(255, channel - rng.randint(10, 35))) for channel in base]
    image = Image.new("RGB", size, tuple(base))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line([(0, y), (width, y)],
                  fill=tuple(int(base[i] + (tint[i] - base[i]) * t) for i in range(3)))
    return image


def _wave_warp(image: Image.Image, amplitude: float, period: float, phase: float) -> Image.Image:
    """Shift each column vertically along a sine wave, wrapping the edges."""
    width, height = image.size
    output = Image.new("RGB", image.size)
    for x in range(width):
        offset = int(round(amplitude * math.sin(2 * math.pi * x / period + phase)))
        column = image.crop((x, 0, x + 1, height))
        output.paste(column, (x, offset))
        output.paste(column, (x, offset - height))
        output.paste(column, (x, offset + height))
    return output


def render_captcha(text: str, seed: int | None = None) -> Image.Image:
    """Render ``text`` as a distorted RGB captcha image."""
    rng = random.Random(seed)
    width, height = IMAGE_SIZE
    image = _gradient_background(rng, IMAGE_SIZE)
    draw = ImageDraw.Draw(image)

    for _ in range(260):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        radius = rng.uniform(0.5, 1.8)
        shade = rng.randint(120, 205)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                     fill=(shade, shade + rng.randint(-15, 15), shade + rng.randint(-15, 15)))

    for _ in range(4):
        x0, x1 = sorted((rng.uniform(-40, width * 0.7), rng.uniform(width * 0.3, width + 40)))
        y0, y1 = sorted((rng.uniform(-20, height * 0.6), rng.uniform(height * 0.4, height + 20)))
        colour = tuple(rng.randint(110, 200) for _ in range(3))
        draw.arc([x0, y0, x1, y1], rng.randint(0, 180), rng.randint(200, 360),
                 fill=colour, width=rng.randint(1, 2))

    margin = 14
    cell = (width - margin * 2) / max(1, len(text))
    for index, char in enumerate(text):
        size = min(52, max(24, int(cell * rng.uniform(0.72, 0.94))))
        font = load_font(size)
        canvas = Image.new("RGBA", (size * 3, size * 3), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(canvas)
        ink = (rng.randint(18, 70), rng.randint(18, 70), rng.randint(30, 90), 255)
        char_draw.text((size * 1.5, size * 1.5), char, font=font, fill=ink, anchor="mm")
        angle = rng.uniform(-30, 30)
        rotated = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
        # A little horizontal shear makes the glyphs less template-like.
        shear = rng.uniform(-0.18, 0.18)
        rotated = rotated.transform(rotated.size, Image.Transform.AFFINE,
                                    (1, shear, -shear * rotated.size[1] / 2, 0, 1, 0),
                                    resample=Image.Resampling.BICUBIC)
        centre_x = margin + index * cell + cell / 2 + rng.uniform(-3, 3)
        centre_y = height / 2 + rng.uniform(-10, 10)
        image.paste(rotated, (int(centre_x - rotated.width / 2), int(centre_y - rotated.height / 2)), rotated)

    image = _wave_warp(image, amplitude=rng.uniform(3.5, 6.0), period=rng.uniform(60, 110),
                       phase=rng.uniform(0, math.tau))
    image = image.rotate(rng.uniform(-1.8, 1.8), resample=Image.Resampling.BICUBIC, fillcolor=(245, 245, 240))

    draw = ImageDraw.Draw(image)
    for _ in range(5):
        colour = tuple(rng.randint(60, 160) for _ in range(3))
        points = []
        amplitude, period = rng.uniform(2, 8), rng.uniform(28, 75)
        phase = rng.uniform(0, math.tau)
        baseline = rng.uniform(10, height - 10)
        for x in range(0, width + 1, 4):
            points.append((x, baseline + amplitude * math.sin(2 * math.pi * x / period + phase)))
        draw.line(points, fill=colour, width=rng.randint(1, 2))

    for _ in range(70):
        x, y = rng.uniform(0, width), rng.uniform(0, height)
        draw.point((x, y), fill=(rng.randint(30, 120),) * 3)

    draw.rectangle([0, 0, width - 1, height - 1], outline=(150, 150, 150), width=2)
    return image.filter(ImageFilter.SMOOTH)


def _char_frequencies() -> dict[str, float]:
    """Map each captcha character to a distinct tone."""
    return {char: 340.0 + index * 46.0 for index, char in enumerate(ALPHABET)}


def render_audio(text: str, seed: int | None = None) -> bytes:
    """Render an audio alternative: one short tone per character plus noise."""
    rng = random.Random(seed)
    frequencies = _char_frequencies()
    samples = array.array("h")
    for char in text:
        frequency = frequencies.get(char, 500.0) * rng.uniform(0.97, 1.04)
        duration = 0.30
        count = int(AUDIO_RATE * duration)
        for n in range(count):
            t = n / AUDIO_RATE
            envelope = min(1.0, n / 80, (count - n) / 80)
            value = (0.42 * math.sin(math.tau * frequency * t)
                     + 0.16 * math.sin(math.tau * frequency * 2 * t))
            value = value * envelope + rng.uniform(-0.035, 0.035)
            samples.append(int(max(-1.0, min(1.0, value)) * 32767))
        for _ in range(int(AUDIO_RATE * 0.10)):
            samples.append(int(rng.uniform(-0.02, 0.02) * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(AUDIO_RATE)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def normalize_answer(answer: str) -> str:
    """Normalise a user answer: uppercase, no spaces or hyphens."""
    return answer.strip().upper().replace(" ", "").replace("-", "")


def _hash_answer(answer: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", normalize_answer(answer).encode("utf-8"), salt, HASH_ROUNDS).hex()


@dataclass(frozen=True)
class Challenge:
    """A freshly created challenge (the answer never leaves the server)."""

    id: str
    answer: str = field(repr=False)
    expires_at: float
    image_png: bytes = field(repr=False)
    audio_wav: bytes = field(repr=False)


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of checking an answer."""

    ok: bool
    reason: str
    remaining_attempts: int = 0


class CaptchaService:
    """Challenge creation, storage and verification."""

    def __init__(self, db_path: Path, ttl: int = DEFAULT_TTL, length: int = DEFAULT_LENGTH,
                 max_attempts: int = DEFAULT_ATTEMPTS, seed: int | None = None) -> None:
        if not 4 <= length <= 8:
            raise ValueError("length must be between 4 and 8")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.db_path = db_path
        self.ttl = ttl
        self.length = length
        self.max_attempts = max_attempts
        self.rng = random.Random(seed)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS challenges (
                    id TEXT PRIMARY KEY,
                    answer_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    image BLOB NOT NULL,
                    audio BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0
                )"""
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS challenges_expiry ON challenges(expires_at)")
            self.conn.commit()

    def create(self, ttl: int | None = None) -> Challenge:
        """Create, render and persist a new challenge."""
        answer = "".join(self.rng.choice(ALPHABET) for _ in range(self.length))
        seed = self.rng.getrandbits(48)
        image = render_captcha(answer, seed=seed)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        audio = render_audio(answer, seed=seed ^ 0x5EED)
        salt = os.urandom(16)
        challenge_id = secrets.token_hex(12)
        now = time.time()
        expires_at = now + (self.ttl if ttl is None else ttl)
        with self.lock:
            self.conn.execute(
                "INSERT INTO challenges VALUES (?,?,?,?,?,?,?,?,?,?)",
                (challenge_id, _hash_answer(answer, salt), salt.hex(), buffer.getvalue(), audio,
                 now, expires_at, 0, self.max_attempts, 0),
            )
            self.conn.execute("DELETE FROM challenges WHERE expires_at < ?", (now - 3600,))
            self.conn.commit()
        return Challenge(challenge_id, answer, expires_at, buffer.getvalue(), audio)

    def verify(self, challenge_id: str, answer: str) -> VerifyResult:
        """Check ``answer`` against the stored hash and update attempt state."""
        with self.lock:
            row = self.conn.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()
            if row is None:
                return VerifyResult(False, "unknown", 0)
            now = time.time()
            if row["used"]:
                return VerifyResult(False, "already used", 0)
            if row["expires_at"] < now:
                return VerifyResult(False, "expired", 0)
            if row["attempts"] >= row["max_attempts"]:
                self.conn.execute("UPDATE challenges SET used=1 WHERE id=?", (challenge_id,))
                self.conn.commit()
                return VerifyResult(False, "too many attempts", 0)
            candidate = _hash_answer(answer, bytes.fromhex(row["salt"]))
            if hmac.compare_digest(candidate, row["answer_hash"]):
                self.conn.execute("UPDATE challenges SET used=1 WHERE id=?", (challenge_id,))
                self.conn.commit()
                return VerifyResult(True, "ok", 0)
            attempts = int(row["attempts"]) + 1
            used = 1 if attempts >= row["max_attempts"] else 0
            self.conn.execute("UPDATE challenges SET attempts=?, used=? WHERE id=?",
                              (attempts, used, challenge_id))
            self.conn.commit()
            remaining = max(0, int(row["max_attempts"]) - attempts)
            reason = "too many attempts" if used else "incorrect"
            return VerifyResult(False, reason, remaining)

    def record(self, challenge_id: str) -> sqlite3.Row | None:
        """Fetch a stored challenge row (image/audio), if it exists."""
        with self.lock:
            return self.conn.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()

    def counts(self) -> dict[str, int]:
        with self.lock:
            total = int(self.conn.execute("SELECT COUNT(*) FROM challenges").fetchone()[0])
            active = int(self.conn.execute(
                "SELECT COUNT(*) FROM challenges WHERE used=0 AND expires_at>?", (time.time(),)
            ).fetchone()[0])
        return {"total": total, "active": active}

    def close(self) -> None:
        self.conn.close()


CSS = """
:root { color-scheme: dark; }
body { margin:0; background:#0f1118; color:#ece9df; font-family: system-ui, -apple-system, sans-serif;
  display:flex; align-items:center; justify-content:center; min-height:100vh; }
.card { width:min(440px, calc(100% - 32px)); background:#181c26; border:1px solid #2b3242;
  border-radius:16px; padding:26px; box-shadow:0 18px 50px rgba(0,0,0,.35); }
h1 { font-size:1.35rem; margin:0 0 6px; letter-spacing:-.02em; }
p { color:#a7b0bf; margin:0 0 16px; line-height:1.5; font-size:.92rem; }
img { width:100%; border-radius:10px; display:block; background:#fff; }
audio { width:100%; margin:12px 0 4px; }
label { display:block; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:#8b96a8;
  margin:16px 0 6px; }
input[type=text] { width:100%; box-sizing:border-box; padding:12px 14px; border-radius:8px;
  border:1px solid #394356; background:#0f131b; color:#fff; font:600 1.15rem ui-monospace, monospace;
  letter-spacing:.18em; text-transform:uppercase; }
button { cursor:pointer; border:0; border-radius:8px; padding:11px 19px; font:600 .92rem system-ui,sans-serif;
  background:#e9b872; color:#241a0c; }
button:hover { filter:brightness(1.07); }
.actions { display:flex; gap:12px; align-items:center; margin-top:18px; flex-wrap:wrap; }
.notice { padding:11px 14px; border-radius:8px; font-size:.9rem; margin:14px 0 0; }
.notice.ok { background:#1c3022; border:1px solid #366044; color:#bfe6c8; }
.notice.bad { background:#33201f; border:1px solid #6d3a36; color:#f0c1bb; }
.meta { font-size:.78rem; color:#778397; margin-top:12px; }
a { color:#e9b872; }
"""


def page(title: str, body: str) -> str:
    """Minimal standalone page."""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>{CSS}</style></head><body><div class="card">{body}</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    """HTTP API and demo form."""

    server_version = "CaptchaMaker/1.0"

    @property
    def service(self) -> CaptchaService:
        return self.server.service  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        if getattr(self.server, "verbose", False):  # type: ignore[attr-defined]
            super().log_message(format, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, markup: str) -> None:
        self._send(status, markup.encode("utf-8"), "text/html; charset=utf-8")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 20_000:
            return {}
        raw = self.rfile.read(length)
        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except (ValueError, UnicodeDecodeError):
                return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace")).items()}

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            challenge = self.service.create()
            body = f"""<h1>Prove you are human</h1>
<p>Type the characters in the image. Letters are not case-sensitive; spaces are ignored.</p>
<img src="/image/{challenge.id}.png" alt="CAPTCHA image" width="280" height="100">
<audio controls src="/audio/{challenge.id}.wav" aria-label="Audio challenge"></audio>
<form method="post" action="/verify">
  <input type="hidden" name="id" value="{challenge.id}">
  <label for="answer">Your answer</label>
  <input id="answer" type="text" name="answer" maxlength="12" autocomplete="off" autocapitalize="characters" required autofocus>
  <div class="actions"><button type="submit">Verify</button>
    <a href="/">New challenge</a></div>
</form>
<p class="meta">Challenge {challenge.id} · expires in {self.service.ttl} seconds ·
{self.service.max_attempts} attempts</p>"""
            self._html(200, page("CAPTCHA", body))
        elif path == "/health":
            self._json(200, self.service.counts())
        elif path.startswith("/image/") and path.endswith(".png"):
            row = self.service.record(path[len("/image/"):-4])
            if row is None:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            else:
                self._send(200, row["image"], "image/png")
        elif path.startswith("/audio/") and path.endswith(".wav"):
            row = self.service.record(path[len("/audio/"):-4])
            if row is None:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            else:
                self._send(200, row["audio"], "audio/wav")
        else:
            self._html(404, page("Not found", "<h1>404</h1><p>No such challenge.</p><p><a href='/'>Try again</a></p>"))

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        data = self._payload()
        if path == "/api/challenge":
            challenge = self.service.create()
            self._json(201, {
                "id": challenge.id,
                "image_url": f"/image/{challenge.id}.png",
                "audio_url": f"/audio/{challenge.id}.wav",
                "expires_in": self.service.ttl,
                "max_attempts": self.service.max_attempts,
            })
        elif path in ("/api/verify", "/verify"):
            challenge_id = str(data.get("id", ""))
            answer = str(data.get("answer", ""))
            result = self.service.verify(challenge_id, answer)
            if path == "/api/verify":
                status = 200
                if result.reason == "unknown":
                    status = 404
                elif result.reason in ("expired", "already used"):
                    status = 410
                elif result.reason == "too many attempts":
                    status = 429
                self._json(status, {"ok": result.ok, "reason": result.reason,
                                    "remaining_attempts": result.remaining_attempts})
            else:
                if result.ok:
                    body = ("<h1>Verified</h1><p class='notice ok'>Correct — you are human.</p>"
                            "<div class='actions'><a href='/'>Another challenge</a></div>")
                    self._html(200, page("Verified", body))
                else:
                    why = {"incorrect": "That answer was not correct.",
                           "expired": "This challenge has expired.",
                           "already used": "This challenge was already solved.",
                           "too many attempts": "Too many attempts; the challenge is closed.",
                           "unknown": "Unknown challenge."}.get(result.reason, result.reason)
                    body = (f"<h1>Not verified</h1><p class='notice bad'>{html.escape(why)}"
                            f"</p><p class='meta'>Remaining attempts: {result.remaining_attempts}</p>")
                    if result.reason == "incorrect":
                        safe_id = html.escape(challenge_id)
                        body += (f"<img src='/image/{safe_id}.png' alt='CAPTCHA image' width='280' height='100'>"
                                 f"<audio controls src='/audio/{safe_id}.wav'></audio>"
                                 "<form method='post' action='/verify'>"
                                 f"<input type='hidden' name='id' value='{safe_id}'>"
                                 "<label for='answer'>Try again</label>"
                                 "<input id='answer' type='text' name='answer' maxlength='12' "
                                 "autocomplete='off' required autofocus>"
                                 "<div class='actions'><button type='submit'>Verify</button>"
                                 "<a href='/'>New challenge</a></div></form>")
                    else:
                        body += "<div class='actions'><a href='/'>Try a new challenge</a></div>"
                    self._html(200 if result.reason == "incorrect" else 410, page("Not verified", body))
        else:
            self._json(404, {"error": "not found"})


def serve(service: CaptchaService, port: int = 8000) -> int:
    """Run the CAPTCHA site until interrupted."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.service = service  # type: ignore[attr-defined]
    host, bound = server.server_address[:2]
    print(f"CAPTCHA Maker at http://{host}:{bound}")
    print("GET / for a challenge; POST /api/challenge and /api/verify for the JSON API.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


def _write_challenge(challenge: Challenge, image_path: Path, audio_path: Path | None) -> None:
    image_path.write_bytes(challenge.image_png)
    if audio_path is not None:
        audio_path.write_bytes(challenge.audio_wav)


def demo() -> int:
    """Verify correct, incorrect, reused and expired challenges."""
    print("CAPTCHA Maker demo")
    print("==================")
    checks: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory(prefix="captcha-") as tmp:
        root = Path(tmp)
        service = CaptchaService(root / "captcha.db", ttl=120, length=5, max_attempts=3, seed=7)
        try:
            challenge = service.create()
            with Image.open(io.BytesIO(challenge.image_png)) as image:
                size = image.size
                colours = len(image.convert("RGB").getcolors(maxcolors=100_000) or [])
            checks.append(("challenge image is a 280x100 PNG", size == IMAGE_SIZE and len(challenge.image_png) > 5_000))
            checks.append((f"image contains visual noise ({colours} colours)", colours > 200))
            checks.append(("audio alternative is a WAV file",
                           challenge.audio_wav[:4] == b"RIFF" and challenge.audio_wav[8:12] == b"WAVE"))
            stored = service.record(challenge.id)
            checks.append(("answers are stored only as salted hashes",
                           stored is not None and len(stored["answer_hash"]) == 64
                           and stored["answer_hash"] != challenge.answer
                           and len(stored["salt"]) == 32))

            result = service.verify(challenge.id, challenge.answer)
            checks.append(("correct answer verifies", result.ok and result.reason == "ok"))
            again = service.verify(challenge.id, challenge.answer)
            checks.append(("challenges are one-time use", not again.ok and again.reason == "already used"))

            goals = service.create()
            wrong = service.verify(goals.id, "ZZZZZ" if goals.answer != "ZZZZZ" else "YYYYY")
            checks.append(("wrong answer is rejected with attempts left",
                           not wrong.ok and wrong.reason == "incorrect" and wrong.remaining_attempts == 2))
            service.verify(goals.id, "ZZZZZ" if goals.answer != "ZZZZZ" else "YYYYY")
            locked = service.verify(goals.id, "ZZZZZ" if goals.answer != "ZZZZZ" else "YYYYY")
            checks.append(("attempt limit closes the challenge", not locked.ok and locked.reason == "too many attempts"))
            after = service.verify(goals.id, goals.answer)
            checks.append(("closed challenge refuses even the right answer",
                           not after.ok and after.reason == "already used"))

            expired = service.create(ttl=-1)
            stale = service.verify(expired.id, expired.answer)
            checks.append(("expired challenge is rejected", not stale.ok and stale.reason == "expired"))

            relaxed = service.create()
            lower = relaxed.answer.lower()
            spaced = " ".join(lower)
            checks.append(("answers are case- and space-insensitive", service.verify(relaxed.id, spaced).ok))

            first, second = service.create(), service.create()
            checks.append(("each challenge renders a distinct image", first.image_png != second.image_png))

            image_path = root / "cli-captcha.png"
            audio_path = root / "cli-captcha.wav"
            _write_challenge(challenge, image_path, audio_path)
            checks.append(("challenge can be saved for CLI use",
                           image_path.stat().st_size > 5_000 and audio_path.stat().st_size > 10_000))
            print(f"  challenge id : {challenge.id}")
            print(f"  image / audio: {image_path.stat().st_size:,} / {audio_path.stat().st_size:,} bytes")

            # ---- HTTP API ----
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.daemon_threads = True
            server.service = service  # type: ignore[attr-defined]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                status, body, _ = _request(f"{base}/api/challenge", json_body={})
                payload = json.loads(body)
                checks.append(("API issues a challenge", status == 201 and "id" in payload
                               and payload["image_url"].endswith(".png")))

                status, image_bytes, _ = _request(f"{base}{payload['image_url']}")
                checks.append(("API serves the challenge image", status == 200 and image_bytes[:8] == b"\x89PNG\r\n\x1a\n"))
                status, audio_bytes, _ = _request(f"{base}{payload['audio_url']}")
                checks.append(("API serves the audio alternative", status == 200 and audio_bytes[:4] == b"RIFF"))

                row = service.record(payload["id"])
                # Solve the API challenge through the service so the demo knows the answer.
                result = service.verify(payload["id"], "WRONG")
                checks.append(("API challenge rejects a wrong answer", not result.ok))
                status, body, _ = _request(f"{base}/api/verify", json_body={"id": payload["id"], "answer": "WRONG"})
                checks.append(("verify API returns JSON failures", status == 200 and json.loads(body)["ok"] is False))

                solved = service.create()
                status, body, _ = _request(f"{base}/api/verify",
                                           json_body={"id": solved.id, "answer": solved.answer})
                checks.append(("verify API accepts a correct JSON answer",
                               status == 200 and json.loads(body)["ok"] is True))

                status, body, _ = _request(f"{base}/api/verify",
                                           json_body={"id": "does-not-exist", "answer": "ABCDE"})
                checks.append(("unknown challenge returns 404", status == 404 and json.loads(body)["reason"] == "unknown"))

                status, page_body, _ = _request(f"{base}/")
                checks.append(("HTML page shows image, audio and a form",
                               status == 200 and b"/image/" in page_body and b"/audio/" in page_body
                               and b'name="answer"' in page_body))

                html_challenge = service.create()
                wrong_answer = "QQQQQ" if html_challenge.answer != "QQQQQ" else "WWWWW"
                status, retry_body, _ = _request(f"{base}/verify",
                                                 data={"id": html_challenge.id, "answer": wrong_answer})
                checks.append(("HTML form offers a retry after a wrong answer",
                               status == 200 and b"Try again" in retry_body))
                status, ok_body, _ = _request(f"{base}/verify",
                                              data={"id": html_challenge.id, "answer": html_challenge.answer})
                checks.append(("HTML form confirms a correct answer", status == 200 and b"Correct" in ok_body))

                status, body, _ = _request(f"{base}/health")
                health = json.loads(body)
                checks.append(("health endpoint reports challenge counts", status == 200 and health["total"] >= 8))
            finally:
                server.shutdown()
                server.server_close()
        finally:
            service.close()

    print()
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    failed = sum(1 for _, ok in checks if not ok)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


def _request(url: str, data: dict[str, str] | None = None,
             json_body: dict[str, Any] | None = None) -> tuple[int, bytes, str]:
    """Small HTTP helper that returns error responses instead of raising."""
    headers = {}
    payload: bytes | None = None
    if json_body is not None:
        payload = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        payload = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(), response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.url or url


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Generate distorted text CAPTCHAs, store hashed answers and verify them.",
        epilog="Run with --demo for a scripted check; with no action it runs an interactive challenge.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted verification walkthrough")
    parser.add_argument("--serve", action="store_true", help="start the HTTP API and demo form")
    parser.add_argument("--port", type=int, default=8000, help="port for --serve (default: 8000)")
    parser.add_argument("--db", type=Path, default=Path("captcha.db"), help="SQLite database path")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL, help="challenge lifetime in seconds")
    parser.add_argument("--length", type=int, default=DEFAULT_LENGTH, help="number of characters (4-8)")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help="allowed attempts per challenge")
    parser.add_argument("--seed", type=int, default=None, help="seed for reproducible glyph layout")
    parser.add_argument("--generate", type=Path, metavar="PNG", help="write a challenge image and exit")
    parser.add_argument("--audio-out", type=Path, metavar="WAV", help="also write the audio alternative")
    parser.add_argument("--show-answer", action="store_true", help="print the answer with --generate")
    parser.add_argument("--verify", nargs=2, metavar=("ID", "ANSWER"), help="verify an answer from the CLI")
    args = parser.parse_args(argv)

    if args.demo:
        return demo()
    if not 4 <= args.length <= 8:
        parser.error("--length must be between 4 and 8")
    if args.ttl < 1 and not args.demo:
        parser.error("--ttl must be positive")

    service = CaptchaService(args.db, ttl=args.ttl, length=args.length,
                             max_attempts=args.attempts, seed=args.seed)
    try:
        if args.verify:
            challenge_id, answer = args.verify
            result = service.verify(challenge_id, answer)
            print(f"{'PASS' if result.ok else 'FAIL'}: {result.reason}"
                  + (f" ({result.remaining_attempts} attempts left)" if not result.ok and result.remaining_attempts else ""))
            return 0 if result.ok else 1
        if args.generate:
            challenge = service.create()
            _write_challenge(challenge, args.generate, args.audio_out)
            print(f"Challenge {challenge.id} written to {args.generate}")
            if args.audio_out:
                print(f"Audio written to {args.audio_out}")
            if args.show_answer:
                print(f"Answer: {challenge.answer}")
            return 0
        if args.serve:
            return serve(service, args.port)

        # Interactive default: generate one, show it, ask once.
        challenge = service.create()
        image_path = Path("captcha.png")
        _write_challenge(challenge, image_path, Path("captcha.wav"))
        print(f"CAPTCHA saved to {image_path} and captcha.wav (challenge {challenge.id})")
        print(f"Expires in {args.ttl} seconds; {service.max_attempts} attempts.")
        try:
            answer = input("Type the characters you see: ")
        except (EOFError, KeyboardInterrupt):
            print("\nNo answer entered.")
            return 1
        result = service.verify(challenge.id, answer)
        if result.ok:
            print("Correct — verified.")
            return 0
        print(f"Not verified: {result.reason}. {result.remaining_attempts} attempt(s) left.")
        return 1
    finally:
        service.close()


if __name__ == "__main__":
    sys.exit(main())
