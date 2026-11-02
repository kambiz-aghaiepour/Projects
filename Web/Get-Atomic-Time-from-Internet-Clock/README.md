# Get Atomic Time from Internet Clock

**Category:** Web · **Project:** Get-Atomic-Time-from-Internet-Clock

## Problem

This program will get the true atomic time from an atomic time clock on the
Internet.

## Features

- SNTP (NTPv4) client over UDP port 123, built directly on `socket` and
  `struct`.
- Multiple samples with a median offset (`--samples`), reducing the effect of a
  single slow packet.
- Standard four-timestamp offset calculation, plus round-trip delay and an
  uncertainty estimate.
- Validates the reply: server mode, stratum (rejects kiss-o'-death and
  unsynchronised servers), and the originate timestamp (anti-spoofing).
- HTTP JSON fallback when UDP is blocked: tries WorldTimeAPI and timeapi.io,
  parsing ISO timestamps with sub-second precision.
- Prints local UTC, corrected UTC and a human explanation of which clock is
  ahead; `--json` emits a machine-readable report.
- `--demo` runs a simulated SNTP server with a known +1.750 s offset on a
  loopback UDP port, then demonstrates a closed-port timeout and the fallback to
  the local clock — fully offline.

## Requirements

Python 3.10+ only; no third-party packages. Outbound UDP to port 123 (or the
configured port) is required for the live SNTP path. No administrator rights are
needed to query a time server.

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --server time.cloudflare.com --samples 5
python3 solution.py --source sntp --server pool.ntp.org --json
python3 solution.py --source http --http-timeout 5
```

| Option | Meaning |
| --- | --- |
| `--server HOST` | NTP/SNTP server (default `pool.ntp.org`). |
| `--port N` | UDP port (default 123). |
| `--timeout SECONDS` | Per-packet timeout (default 3). |
| `--samples N` | Number of SNTP samples; the median offset is reported (default 3). |
| `--source {auto,sntp,http}` | Force a source; `auto` tries SNTP then HTTP (default). |
| `--http-url URL` | Custom JSON time endpoint, tried before the built-ins. |
| `--http-timeout SECONDS` | HTTP timeout (default 5). |
| `--json` | Print a JSON report instead of the formatted one. |
| `--demo` | Run the offline demonstration. |

The program only reports the corrected time; it does not change the system
clock. Setting the clock would require administrator privileges and is left to
the operating system's own NTP service.

## Example Output

```
Atomic Time demo (offline: one simulated SNTP server, then a failure path)

1. Simulated SNTP server on 127.0.0.1:51122 with a +1.750 s clock
   sample 1: offset +1.7503 s, round trip 0.00 ms
   sample 2: offset +1.7503 s, round trip 0.00 ms
   sample 3: offset +1.7503 s, round trip 0.00 ms

Source:        SNTP 127.0.0.1:51122
Detail:        3 samples, median offset
Round trip:    0.0 ms
Clock offset:  +1.7503 s (server is ahead by 1.750 s)
Local UTC:     2026-11-02 19:05:17.829 UTC
Corrected UTC: 2026-11-02 19:05:19.579 UTC
Uncertainty:   about ±0.0 ms (half the round trip)

2. Simulated network outage (closed UDP port, 0.4 s timeout)
   SNTP unavailable: SNTP request to 127.0.0.1:57255 timed out after 0.4s
   HTTP fallback skipped in this offline demo.
   Showing local clock instead: 2026-11-02 19:05:18.430 UTC
   Without a reachable time source only the local clock is available;
   rerun without --demo and with network access to obtain a correction.

Demo complete: simulated offset verified, offline path handled gracefully.
```

The loopback round trip is effectively zero, so the demo's uncertainty displays
as 0.0 ms; a real Internet server typically shows 1–100 ms.

## Implementation Notes

An SNTP request is a 48-byte packet with the first byte set to `0x23`
(LI=0, version 4, mode 3); the transmit timestamp occupies bytes 40–47. The
reply supplies `T2` (server receive), `T3` (server transmit) and echoes `T1`
(originate); the client measures `T4` on arrival. The offset is
`((T2 − T1) + (T3 − T4)) / 2` and the round-trip delay is
`(T4 − T1) − (T3 − T2)`. Timestamps are 64-bit fixed point: seconds since
1900-01-01 plus a 32-bit fraction, converted to Unix time by subtracting
2,208,988,800.

Samples are taken sequentially and the median offset is chosen; the best
round-trip sample supplies the uncertainty estimate. A reply whose originate
timestamp does not match the request is discarded. The HTTP fallback is less
accurate because only one timestamp is available: the server's time is compared
with the midpoint of the request, and `unixtime` fields have one-second
resolution.

Limitations: the client does not authenticate NTP (NTS), does not adjust the
system clock, and cannot compensate for highly asymmetric network paths. Some
corporate or public networks block outbound UDP/123, which is exactly when the
HTTP fallback is used.
