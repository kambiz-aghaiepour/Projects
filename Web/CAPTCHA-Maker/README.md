# CAPTCHA Maker

## Problem

> Create an image with letters and numbers for signup forms, then ask the user
> to enter what they see. It keeps web bots from automatically signing up and
> spamming.

This is project **CAPTCHA Maker** in the **Web** category of the Mega Project
List.

## Features

- **Distorted text images** rendered with Pillow: per-character rotation and
  shear, random fonts/sizes/colours, sine-wave column displacement, overlapping
  arcs, curved interference lines, speckles and a gentle blur. Five characters
  drawn from an unambiguous alphabet (`I`, `O`, `0`, `1` are excluded).
- **Audio alternative**: a WAV of one tone per character with pitch jitter and
  background noise, offered alongside every challenge.
- **Hashed answers only**: each challenge stores a 16-byte random salt and a
  PBKDF2-HMAC-SHA256 digest (120,000 rounds), never the plaintext.
- **Expiry** (default 300 s), **attempt limit** (default 3), and **one-time
  use** enforced in SQLite.
- **JSON API**: `POST /api/challenge` issues a challenge; `POST /api/verify`
  checks `{id, answer}` and returns `ok`, `reason` and remaining attempts.
- **HTML demo form** at `/` with image, audio player and answer box.
- **CLI**: generate an image/audio pair, or verify a stored challenge by id.
- Case- and space-insensitive answers (`"676 nm"` matches `676NM`).

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

On hosts with a managed Python (PEP 668), use a virtual environment:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Scripted check: rendering, hashing, expiry, attempts, API
python3 solution.py --demo

# Serve the demo form and JSON API
python3 solution.py --serve --port 8000

# Generate one challenge for use elsewhere
python3 solution.py --generate captcha.png --audio-out captcha.wav --show-answer

# Verify an answer later (same --db file)
python3 solution.py --verify <challenge-id> "AB3DE"

# Generate and answer interactively
python3 solution.py

python3 solution.py --help
```

| Option | Meaning |
| --- | --- |
| `--demo` | Render several challenges and verify correct/incorrect/expired/reused |
| `--serve` | Start the HTTP API and HTML form |
| `--port N` | Port for `--serve` (default 8000) |
| `--db PATH` | SQLite file holding challenges (default `captcha.db`) |
| `--ttl N` | Seconds before a challenge expires (default 300) |
| `--length N` | Characters per challenge, 4–8 (default 5) |
| `--attempts N` | Wrong answers allowed (default 3) |
| `--seed N` | Seed glyph layout for reproducible images |
| `--generate PNG` | Write a challenge image and print its id |
| `--audio-out WAV` | Also write the audio challenge |
| `--show-answer` | Print the answer (testing only) |
| `--verify ID ANSWER` | Check an answer from the command line |

### API

```bash
curl -s -X POST http://127.0.0.1:8000/api/challenge
# {"id":"…","image_url":"/image/….png","audio_url":"/audio/….wav",
#  "expires_in":300,"max_attempts":3}

curl -s -X POST http://127.0.0.1:8000/api/verify \
  -H 'Content-Type: application/json' -d '{"id":"…","answer":"AB3DE"}'
# {"ok":true,"reason":"ok","remaining_attempts":0}
```

`reason` is one of `ok`, `incorrect`, `expired`, `already used`,
`too many attempts`, `unknown`. HTTP status is `404` for unknown ids, `410` for
expired/used and `429` when the attempt limit is exhausted.

## Example Output

```text
$ python3 solution.py --demo
CAPTCHA Maker demo
==================
  challenge id : d5faf1b492bd926ad161bb90
  image / audio: 43,110 / 88,244 bytes

  [PASS] challenge image is a 280x100 PNG
  [PASS] image contains visual noise (8066 colours)
  [PASS] audio alternative is a WAV file
  [PASS] answers are stored only as salted hashes
  [PASS] correct answer verifies
  [PASS] challenges are one-time use
  [PASS] wrong answer is rejected with attempts left
  [PASS] attempt limit closes the challenge
  [PASS] closed challenge refuses even the right answer
  [PASS] expired challenge is rejected
  [PASS] answers are case- and space-insensitive
  [PASS] each challenge renders a distinct image
  [PASS] challenge can be saved for CLI use
  [PASS] API issues a challenge
  [PASS] API serves the challenge image
  [PASS] API serves the audio alternative
  [PASS] API challenge rejects a wrong answer
  [PASS] verify API returns JSON failures
  [PASS] verify API accepts a correct JSON answer
  [PASS] unknown challenge returns 404
  [PASS] HTML page shows image, audio and a form
  [PASS] HTML form offers a retry after a wrong answer
  [PASS] HTML form confirms a correct answer
  [PASS] health endpoint reports challenge counts

24/24 checks passed
```

## Implementation Notes

- `render_captcha()` draws a pastel gradient, speckles and arcs, then renders
  each glyph on a transparent 3×-size canvas, rotates it (±30°), applies a
  small affine shear and pastes it into its horizontal cell. The whole image is
  column-warped along a sine wave (columns are wrapped vertically so no blank
  bands appear), tilted slightly, then crossed with curved noise lines and a
  final blur.
- `render_audio()` maps every character to a distinct frequency and writes a
  mono 16-bit 22.05 kHz WAV using the standard library `wave` module. It is an
  accessibility aid, not a high-security audio CAPTCHA.
- `CaptchaService` keeps a `sqlite3` connection behind a lock, stores PNG/WAV
  blobs directly, and compares digests with `hmac.compare_digest`. Verification
  checks used → expired → attempts → hash, then marks the row used on success
  or after the final attempt.
- The demo runs against a temporary database and an ephemeral `127.0.0.1:0`
  server. Images are checked by reopening them with Pillow; the answer is
  obtained from the creation result (the HTTP handler never returns it).
- Verification is an O(1) SQLite lookup plus a fixed-cost PBKDF2 computation;
  each challenge stores one PNG and one WAV blob.
- Limitations: a determined OCR model can still read many captchas, and the
  tone-based audio alternative is machine-decodable by design. For production,
  add rate limiting per IP and consider proof-of-work or a third-party service.
