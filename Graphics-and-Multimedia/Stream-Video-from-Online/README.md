# Stream Video from Online

**Category:** Graphics-and-Multimedia · **Project:** Stream-Video-from-Online

## Problem

> Try to create your own online streaming video player.

## Features

- A dependency-free HTTP streaming server (`ThreadingHTTPServer`) that serves
  one video file plus a generated HTML5 player page.
- Full byte-range support: `bytes=start-end`, open-ended `bytes=start-`,
  suffix `bytes=-N`, `HEAD` requests, and `416 Range Not Satisfiable` with
  `Content-Range: bytes */size` for impossible ranges.
- Correct `206 Partial Content`, `Content-Length`, `Content-Range`,
  `Accept-Ranges: bytes`, `Last-Modified` and video MIME headers, so browsers
  can start playback immediately and seek by jumping to a byte offset.
- Player page uses native `<video controls>` for seeking, plus a live panel
  showing duration, position, buffered ranges, ready state and the result of an
  explicit `Range: bytes=0-1023` probe. Includes 25/50/75% seek buttons.
- Demo generates a three-second MP4 with `ffmpeg` (or a small fallback
  header file when ffmpeg is absent), starts the server on an ephemeral port, and
  verifies the protocol with real HTTP requests.
- Binds to localhost by default; `--host 0.0.0.0` exposes it on the LAN.

## Requirements

Python 3.10+ and the standard library only. `ffmpeg` is optional and used only
by the demo to synthesise a test clip and by nothing at serve time.

## Usage

```bash
# Scripted demo: generate a clip, start a server, probe ranges, shut down
python3 solution.py --demo

# Stream your own file at http://127.0.0.1:8000/
python3 solution.py movie.mp4

# Another port, open a browser, log every Range request
python3 solution.py movie.webm --port 8080 --open --verbose

# Share on the local network
python3 solution.py movie.mp4 --host 0.0.0.0 --port 8000
```

| Option | Meaning |
| --- | --- |
| `FILE` | Video to serve (`.mp4`, `.webm`, `.ogv`, `.mov`, `.mkv`, `.avi`, …) |
| `--host` | Bind address (default `127.0.0.1`) |
| `--port` | Port, `0` picks a free one (default `8000`) |
| `--open` | Open the player in the default browser |
| `--verbose` | Log requests and their `Range` headers |
| `--demo` | Run the self-checking demo |

## Example Output

```text
Stream Video from Online demo
  video    : sample.mp4 (216.0 KiB, generated with ffmpeg)
  server   : http://127.0.0.1:45197  (ephemeral port, background thread)
  range probes:
    [PASS] player page      HTTP 200, 4891 bytes
    [PASS] HEAD media       HTTP 200, length=221136, accept-ranges=bytes
    [PASS] range 0-99       HTTP 206, 100 bytes, Content-Range: bytes 0-99/221136
    [PASS] range 110568-    HTTP 206, 110568 bytes
    [PASS] suffix range -64 HTTP 206, 64 bytes
    [PASS] out-of-range     HTTP 416, Content-Range: bytes */221136
    [PASS] full download    HTTP 200, 221136 bytes, video/mp4
  result   : 7/7 checks passed
Demo complete: run without --demo to serve your own video and open the player in a browser.
```

## Implementation Notes

- `parse_range()` uses one regex for the single-range forms browsers send.
  Multi-range requests are rejected with `416`; in practice browsers use one
  range for media seeking.
- The response body is copied in 64 KiB chunks from the requested offset, so
  memory use is constant regardless of file size. A browser that abandons a
  request mid-stream (`BrokenPipeError` / `ConnectionResetError`) is handled
  silently — that is normal behaviour when the user seeks.
- The player page is generated per request from a `string.Template`, with the
  filename URL-quoted into the `<video src>` and the range probe. The page has
  no external assets, so it works offline.
- Port `0` asks the OS for a free port; the demo prints the resulting URL and
  shuts the server down in a `finally` block.
- Limitations: one file per server instance, no authentication, no TLS, and no
  multi-range or HLS/DASH segmentation. Serve behind a reverse proxy if you
  need HTTPS. The fallback header file used when ffmpeg is missing is not playable; it
  exists so the protocol checks can still run.
