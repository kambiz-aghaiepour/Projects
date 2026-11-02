# E-Card Generator

## Problem

> Make a site that allows people to generate their own little e-cards and send
> them to other people. Do not use Flash. Use a picture library and perhaps
> insightful mottos or quotes.

This is project **E-Card Generator** in the **Web** category of the Mega Project
List.

## Features

- Pick a recipient, sender, message and one of six visual themes (sunset, ocean,
  forest, night, candy, paper).
- Cards are rendered **server-side with Pillow** to a 960×640 PNG: two-colour
  gradient, theme-specific motifs (hearts, bubbles, leaves, stars, confetti,
  lines), double border, wrapped serif message and signature.
- A public HTML card page at `/card/<id>` with a share link and PNG download.
- Gallery at `/gallery` showing the most recent cards.
- "Insert a motto" button pulls one of six built-in quotes from `/api/quote`.
- SQLite stores card metadata, so the gallery survives restarts; PNGs live in a
  configurable cards directory.
- Offline rendering from the command line with `--render`.
- Input validation (required fields, 600-character message cap, known theme)
  with friendly `400` pages and `404` for unknown cards.
- No Flash, no JavaScript framework, no external assets or network calls.

## Requirements

Python 3.10+ and Pillow:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scripted verification: offline render + HTTP walkthrough
python3 solution.py --demo

# Run the site (default action), serving on 127.0.0.1:8000
python3 solution.py
python3 solution.py --serve --port 9000 --db site.db --cards-dir cards

# Render one card without starting a server
python3 solution.py --render hello.png --to "Grace Hopper" \
  --from "Ada" --theme ocean --message "Thanks for debugging the impossible."

# Other options
python3 solution.py --list-themes
python3 solution.py --help
```

| Option | Meaning |
| --- | --- |
| `--demo` | Full offline + localhost verification, exits 0 |
| `--serve` | Start the HTTP server (implicit when no action is given) |
| `--port N` | Listening port for `--serve` (default 8000) |
| `--db PATH` | SQLite database file (default `e-cards.db`) |
| `--cards-dir PATH` | Where rendered PNGs are written (default `cards/`) |
| `--render PNG` | Render one card offline to `PNG` |
| `--to`, `--from`, `--message`, `--theme`, `--seed` | Inputs for `--render`; `--seed` makes motif placement reproducible |
| `--list-themes` | Print theme names and motif styles |
| `--verbose` | Log HTTP requests |

## Example Output

```text
$ python3 solution.py --demo
E-Card Generator demo
=====================
  offline card : offline-card.png (50,926 bytes, 3,814 colours)
  http card id : 62a4a01f
  cards on disk: 2

  [PASS] offline render produced a PNG
  [PASS] PNG dimensions are 960x640
  [PASS] PNG has visual detail (3814 colours)
  [PASS] GET / serves the creation form
  [PASS] POST /create redirects to a card page
  [PASS] card page shows the recipient and message
  [PASS] served card image is a valid PNG
  [PASS] card file exists on disk
  [PASS] gallery lists both cards
  [PASS] motto API returns JSON
  [PASS] invalid form returns 400 with an error
  [PASS] missing image returns 404

12/12 checks passed
```

## Implementation Notes

- `CardStore` keeps a single `sqlite3` connection guarded by a lock; the HTTP
  server is a `ThreadingHTTPServer`, so handlers may run concurrently.
- Cards get an 8-hex-character random id used both as the database key and PNG
  filename. A collision check retries before inserting.
- `render_card()` draws a per-row vertical gradient, scatters seeded motif
  shapes with `random.Random(seed)`, wraps text with a greedy word-wrap based on
  `ImageDraw.textlength`, and shrinks the message font when a card would need
  more than eight lines. Fonts are discovered from common Linux/macOS/Windows
  paths and fall back to Pillow's default.
- The demo uses a temporary directory and an ephemeral port (`127.0.0.1:0`),
  posts real forms with `urllib`, and always shuts the server down in a
  `finally` block.
- Rendering costs O(width × height) for the gradient and wave/noise work plus
  O(message length) for wrapping; the demonstration stays well under a second.
- Limitations: cards are public to anyone with the link (no accounts or
  expiry), and images are raster PNGs rather than print-resolution assets.
