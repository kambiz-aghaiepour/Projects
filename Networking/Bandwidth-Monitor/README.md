# Bandwidth Monitor

## Problem

A small utility that tracks how much data you have uploaded and downloaded
from the network during your current online session and generates a report.

Part of the **Networking** category in the Mega Project List.

## Features

- Reads cumulative RX/TX byte and packet counters from `/proc/net/dev`.
- Samples twice (or `--count` times) and reports per-interface throughput.
- Human-readable byte units (`KiB`, `MiB`, `GiB`) and per-second rates.
- Session totals accumulated for as long as the program runs.
- Interface filtering, interface listing and JSON output.
- `--demo` generates 64 KiB of loopback traffic and measures it across two
  samples 0.3 seconds apart, using live kernel counters.

## Requirements

Python 3.10+ on Linux (`/proc/net/dev` is required for live monitoring). No
third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --interval 2 --count 5
python3 solution.py --interface eth0 --interface wlan0 --interval 1 --count 10
python3 solution.py --list
python3 solution.py --count 3 --json
```

| Option | Meaning |
| --- | --- |
| `-i, --interface` | Monitor only this interface; repeat for several. |
| `-n, --count` | Number of sample windows to report (default `1`). |
| `-s, --interval` | Seconds between counter snapshots (default `1.0`). |
| `--list` | Print all interfaces with cumulative counters, then exit. |
| `--json` | Emit per-window rates and session totals as JSON. |
| `--demo` | Run the offline self-test (local traffic only). |

## Example Output

```
$ python3 solution.py --demo
Interfaces detected: enp5s0, enp8s0, lo, wlp7s0

Demo generated 64 KiB of loopback traffic between the two samples.

Demo bandwidth report
Sample window: 0.30s
----------------------------------------------------------------------------
Interface       Downloaded      Uploaded        Down rate          Up rate
----------------------------------------------------------------------------
lo                73.8 KiB      73.8 KiB      245.7 KiB/s      245.7 KiB/s
----------------------------------------------------------------------------
TOTAL             73.8 KiB      73.8 KiB      245.7 KiB/s      245.7 KiB/s

Session totals (demo)
----------------------------------------------------------------------------
lo                73.8 KiB      73.8 KiB          59 pkts          59 pkts
----------------------------------------------------------------------------
TOTAL             73.8 KiB      73.8 KiB

Demo complete: counters parsed and rates computed from live data.
```

## Implementation Notes

`/proc/net/dev` exposes monotonic counters per interface; the program snapshots
them, sleeps, snapshots again and subtracts. The RX byte counter is field 1 and
the TX byte counter is field 9 after the interface name. Negative deltas
(counter resets or interface re-creation) are clamped to zero. Rates divide by
the measured `time.monotonic()` interval rather than the requested one, so
scheduler delays do not inflate throughput. Demo traffic is sent over
loopback, which is locally generated and needs no external network.

Session totals cover the lifetime of this process, not the operating system's
login session, and counters include every process on the machine — there is no
per-process attribution. Non-Linux systems do not expose this interface.
