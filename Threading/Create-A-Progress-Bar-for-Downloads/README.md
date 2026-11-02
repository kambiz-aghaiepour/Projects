# Create a Progress Bar for Downloads

*Category: `Threading` — project directory: `Threading/Create-A-Progress-Bar-for-Downloads/`.*

## Problem

Create a progress bar for applications that can keep track of a download in
progress. The progress bar will be on a separate thread and will communicate
with the main thread using delegates.

## Features

- **Background download worker** — a dedicated thread streams the file over
  HTTP(S), reads fixed-size chunks, and never touches the terminal.
- **Main-thread renderer** — immutable `ProgressEvent` messages travel over a
  `queue.Queue`; the main thread draws the bar (percentage, downloaded/total,
  transfer rate, ETA) and is the only writer to the output stream, mirroring a
  UI thread that marshals delegate callbacks.
- **Live TTY bar** — redraws in place with `\r`; when piped or captured, emits
  one clean line per 10 % step instead of carriage-return noise.
- **Resumable downloads** — writes to `<name>.part`, sends an HTTP `Range`
  request on `--resume`, handles `206 Partial Content`, and detects servers
  that ignore ranges.
- **Robust failure handling** — connection errors, 404s, truncated responses,
  and interrupted transfers produce clear messages; partial data stays on disk
  for a later resume.
- **`--quiet`** — suppresses the bar and summary while still downloading and
  verifying the payload.
- **Self-contained demo** — spins up a throttled loopback `http.server` with
  range support, then exercises a full download, a dropped-then-resumed
  transfer, and quiet mode.

## Requirements

Python 3.10+ and the standard library only. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py https://example.com/file.iso
python3 solution.py https://example.com/file.iso -o downloads/file.iso
python3 solution.py https://example.com/file.iso --resume
python3 solution.py https://example.com/file.iso -q
```

| Option | Meaning |
| --- | --- |
| `url` | HTTP(S) address to download (prompted for when omitted; not needed with `--demo`). |
| `-o, --output PATH` | Destination file; defaults to the URL's basename. |
| `-q, --quiet` | Hide the progress bar and the final summary. |
| `--resume` | Continue from an existing `<output>.part` using `Range`. |
| `--chunk-size BYTES` | Read size per iteration (default 64 KiB, minimum 1024). |
| `--timeout SECONDS` | Socket timeout (default 20). |
| `--demo` | Run the scripted local-server demonstration and exit. |

Progress is written to stderr, so stdout stays free for scripting. Press
Ctrl+C to cancel; the worker stops at the next chunk boundary and the partial
file is kept for `--resume`.

## Example Output

Trimmed `--demo` output (captured non-interactively, where the bar prints one
line per 10 % step):

```
Progress bar demo: worker thread downloads, main thread renders.
Loopback server: http://127.0.0.1:33807/sample.bin (3.00 MiB, throttled)

[1/3] Straight download
full download  [------------------------------]   2.1% 64.00 KiB/3.00 MiB 1.25 MiB/s ETA 00:02
full download  [###---------------------------]  10.4% 320.00 KiB/3.00 MiB 3.88 MiB/s ETA 00:01
full download  [###############---------------]  50.0% 1.50 MiB/3.00 MiB 3.24 MiB/s ETA 00:00
full download  [##############################] 100.0% 3.00 MiB/3.00 MiB 3.17 MiB/s ETA 00:00
  -> completed, 3.00 MiB written, sha256 verified

[2/3] Interrupted transfer, then resume
attempt 1      [#########---------------------]  31.2% 960.00 KiB/3.00 MiB 3.33 MiB/s ETA 00:01
  -> interrupted: 1.19 MiB kept in resumed.bin.part
  resuming at byte 1,245,184
resume         [##############################] 100.0% 3.00 MiB/3.00 MiB 3.22 MiB/s ETA 00:00
  -> completed from byte 1,245,184, sha256 verified

[3/3] Quiet mode
  -> no progress lines emitted; file complete: True

Demo complete: 3/3 checks passed.
```

## Implementation Notes

- **Architecture.** `Downloader(threading.Thread)` owns the socket and file
  handle and posts `ProgressEvent` records (`start`, `progress`, `notice`,
  `done`, `interrupted`, `cancelled`, `error`) to a bounded queue. The main
  thread drains the queue and calls `ProgressBar.update()`; no locks or shared
  mutable counters are needed.
- **Delegates in Python.** The problem's "delegates" map to callables/events
  marshalled across threads. Passing messages through a queue, rather than
  invoking the widget from the worker, is the thread-safe equivalent of
  `Control.Invoke`/`Dispatcher.Invoke` in GUI toolkits.
- **Rate and ETA.** The bar uses an exponentially weighted moving average of
  instantaneous chunk rates (30 % new / 70 % previous) for responsiveness;
  overall average bytes/second drives ETA so it does not jitter wildly.
- **Resume correctness.** Downloads always land in `<output>.part` and are
  atomically renamed with `Path.replace` only after the byte count matches
  `Content-Length` (or `Content-Range`'s total). A `200` response to a range
  request resets the offset and restarts cleanly; `416` produces an actionable
  error.
- **Limitations.** One connection at a time, no redirect authentication, and
  no expected-digest option — compare the printed SHA-256 against a trusted
  value yourself. Unknown-length (chunked) responses display bytes and rate
  without percentage or ETA.
