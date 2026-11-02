# Port Scanner

## Problem

Enter an IP address and a port range; the program attempts to connect to each
port and marks any successful connection as open.

Part of the **Networking** category in the Mega Project List.

## Features

- Accepts IP addresses or hostnames, including IPv6 targets.
- Port specifications such as `22,80,443` or `1-1024,8000-8100`.
- Concurrent TCP connect scans with configurable workers and per-port timeout.
- Service labels from the system services database (e.g. `22/tcp (ssh)`).
- Human-readable report or machine-readable `--json` output.
- `--demo` starts a listener on a free local port and scans a three-port range
  around it, verifying that only the listener is reported open.

## Requirements

Python 3.10+ and its standard library. No third-party packages.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 192.168.1.10 -p 1-1024
python3 solution.py example.com -p 22,80,443 --timeout 0.3 --workers 50
python3 solution.py 127.0.0.1 -p 8000-8100 --json
```

| Option | Meaning |
| --- | --- |
| `target` | IP address or hostname to scan (required unless `--demo`). |
| `-p, --ports` | Comma-separated ports and ranges (default `1-1024`). |
| `-t, --timeout` | Per-port connect timeout in seconds (default `0.5`). |
| `-w, --workers` | Number of concurrent probe threads (default `100`). |
| `--json` | Emit a JSON document with target, address, timing and open ports. |
| `--demo` | Run the offline self-test with a local listener. |

## Example Output

```
$ python3 solution.py --demo
Demo listener started on 127.0.0.1:37583
Scanning 127.0.0.1 ports 37583-37585

Scan results for 127.0.0.1
------------------------------------------------
  OPEN  37583/tcp
------------------------------------------------
1 open / 3 scanned in 0.00s
Demo verified: the local listener was the only open port detected.
```

## Implementation Notes

Each port is probed with `socket.create_connection`, so the scanner completes a
normal TCP three-way handshake and immediately closes it. This needs no root
privileges and works through ordinary user sockets, unlike SYN/half-open scans.
Ports are distributed over a `ThreadPoolExecutor`; total runtime is roughly
`ceil(ports / workers) * timeout` for filtered ports. A refused connection is
reported as closed, while a timeout is treated as closed/filtered — the report
does not distinguish the two. The scanner does not grab banners or attempt
service identification beyond the local `getservbyport` table. Hostnames are
resolved to the first stream address returned by `getaddrinfo` (IPv4 or IPv6);
scan a literal address when you need to choose a family explicitly.
