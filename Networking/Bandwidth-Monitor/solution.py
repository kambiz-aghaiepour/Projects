#!/usr/bin/env python3
"""Session bandwidth monitor based on /proc/net/dev counters.

Takes two or more counter snapshots, computes per-interface throughput and
prints a session report.  On systems without /proc/net/dev the program falls
back to a clearly labelled synthetic demonstration, so ``--demo`` always works.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PROC_NET_DEV = Path("/proc/net/dev")


@dataclass(frozen=True)
class InterfaceCounters:
    """Cumulative byte and packet counters for one interface."""

    rx_bytes: int
    rx_packets: int
    tx_bytes: int
    tx_packets: int


@dataclass
class InterfaceTotals:
    """Accumulated traffic measured during this session."""

    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    seconds: float = 0.0


def read_counters(path: Path = PROC_NET_DEV) -> dict[str, InterfaceCounters]:
    """Parse /proc/net/dev into a mapping of interface name to counters."""
    counters: dict[str, InterfaceCounters] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    for line in lines[2:]:
        name, sep, rest = line.partition(":")
        if not sep:
            continue
        fields = rest.split()
        if len(fields) < 16:
            continue
        try:
            counters[name.strip()] = InterfaceCounters(
                rx_bytes=int(fields[0]),
                rx_packets=int(fields[1]),
                tx_bytes=int(fields[8]),
                tx_packets=int(fields[9]),
            )
        except ValueError:
            continue
    return counters


def human_bytes(value: float) -> str:
    """Format a byte count with binary units."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{sign}{value:.1f} {unit}" if unit != "B" else f"{sign}{int(value)} B"
        value /= 1024
    return f"{sign}{value:.1f} TiB"


def human_rate(bytes_per_second: float) -> str:
    """Format a throughput figure."""
    return f"{human_bytes(bytes_per_second)}/s"


def _delta(current: int, previous: int) -> int:
    """Counter difference, tolerating a reset/wrap."""
    difference = current - previous
    return difference if difference >= 0 else 0


def collect_totals(
    previous: dict[str, InterfaceCounters],
    current: dict[str, InterfaceCounters],
    seconds: float,
    interfaces: list[str] | None,
) -> dict[str, InterfaceTotals]:
    """Compute traffic totals between two snapshots."""
    names = interfaces or sorted(set(previous) | set(current))
    totals: dict[str, InterfaceTotals] = {}
    for name in names:
        if name not in current:
            continue
        before = previous.get(name, InterfaceCounters(0, 0, 0, 0))
        after = current[name]
        totals[name] = InterfaceTotals(
            rx_bytes=_delta(after.rx_bytes, before.rx_bytes),
            tx_bytes=_delta(after.tx_bytes, before.tx_bytes),
            rx_packets=_delta(after.rx_packets, before.rx_packets),
            tx_packets=_delta(after.tx_packets, before.tx_packets),
            seconds=max(seconds, 1e-9),
        )
    return totals


def print_report(
    totals: dict[str, InterfaceTotals],
    seconds: float,
    title: str = "Bandwidth report",
) -> None:
    """Print a table of per-interface throughput for one sample window."""
    print(title)
    print(f"Sample window: {seconds:.2f}s")
    print("-" * 76)
    print(f"{'Interface':<12}{'Downloaded':>14}{'Uploaded':>14}"
          f"{'Down rate':>17}{'Up rate':>17}")
    print("-" * 76)
    for name, item in totals.items():
        print(f"{name:<12}{human_bytes(item.rx_bytes):>14}{human_bytes(item.tx_bytes):>14}"
              f"{human_rate(item.rx_bytes / item.seconds):>17}"
              f"{human_rate(item.tx_bytes / item.seconds):>17}")
    print("-" * 76)
    total_rx = sum(item.rx_bytes for item in totals.values())
    total_tx = sum(item.tx_bytes for item in totals.values())
    print(f"{'TOTAL':<12}{human_bytes(total_rx):>14}{human_bytes(total_tx):>14}"
          f"{human_rate(total_rx / max(seconds, 1e-9)):>17}"
          f"{human_rate(total_tx / max(seconds, 1e-9)):>17}")


def print_session(session: dict[str, InterfaceTotals],
                  title: str = "Session totals (since monitoring started)") -> None:
    """Print cumulative traffic measured since the program started."""
    if not session:
        return
    print(f"\n{title}")
    print("-" * 76)
    for name, item in session.items():
        print(f"{name:<12}{human_bytes(item.rx_bytes):>14}{human_bytes(item.tx_bytes):>14}"
              f"{item.rx_packets:>12} pkts{item.tx_packets:>12} pkts")
    print("-" * 76)
    grand_rx = sum(item.rx_bytes for item in session.values())
    grand_tx = sum(item.tx_bytes for item in session.values())
    print(f"{'TOTAL':<12}{human_bytes(grand_rx):>14}{human_bytes(grand_tx):>14}")


def _generate_loopback_traffic(amount: int = 64 * 1024) -> None:
    """Send a little data over loopback so the demo has something to measure."""
    import socket

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(5)
    port = server.getsockname()[1]

    def drain() -> None:
        try:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            remaining = amount
            with conn:
                while remaining > 0:
                    chunk = conn.recv(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
        finally:
            server.close()

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.sendall(b"x" * amount)
    finally:
        thread.join(timeout=5)


def _synthetic_snapshot(step: int) -> dict[str, InterfaceCounters]:
    """Deterministic counters used when procfs is unavailable."""
    return {"demo0": InterfaceCounters(
        rx_bytes=step * 65536,
        rx_packets=step * 128,
        tx_bytes=step * 32768,
        tx_packets=step * 64,
    )}


def run_demo() -> int:
    """Sample /proc/net/dev twice with a short sleep and report the delta."""
    synthetic = False
    before: dict[str, InterfaceCounters] = {}
    after: dict[str, InterfaceCounters] = {}
    seconds = 0.0
    if PROC_NET_DEV.exists():
        try:
            before = read_counters()
            print(f"Interfaces detected: {', '.join(sorted(before))}")
            _generate_loopback_traffic(64 * 1024)
            started = time.monotonic()
            time.sleep(0.3)
            after = read_counters()
            seconds = time.monotonic() - started
        except RuntimeError as exc:
            print(f"Live counters unavailable ({exc}); using synthetic demo data.")
            synthetic = True
    else:
        print(f"{PROC_NET_DEV} is unavailable on this platform; "
              "using synthetic demo data.")
        synthetic = True

    if synthetic:
        before = _synthetic_snapshot(0)
        time.sleep(0.3)
        after = _synthetic_snapshot(1)
        seconds = 0.3

    # Focus the demo table on loopback, or the synthetic interface as fallback.
    if synthetic:
        names = ["demo0"]
    else:
        names = [name for name in ("lo",) if name in after]
        if not names:
            names = [name for name in after if name != "lo"][:2]
    totals = collect_totals(before, after, seconds, names or None)
    session = {name: InterfaceTotals(
        rx_bytes=item.rx_bytes, tx_bytes=item.tx_bytes,
        rx_packets=item.rx_packets, tx_packets=item.tx_packets,
        seconds=item.seconds,
    ) for name, item in totals.items()}

    if synthetic:
        print("\nDemo used synthetic counters; no live interface was sampled.\n")
    else:
        print("\nDemo generated 64 KiB of loopback traffic between the two samples.\n")
    print_report(totals, seconds, "Demo bandwidth report")
    print_session(session, "Session totals (demo)")
    if not totals:
        print("No interfaces matched; nothing to report.", file=sys.stderr)
        return 1
    if synthetic:
        print("\nDemo complete: synthetic counters sampled and rates computed.")
    else:
        print("\nDemo complete: counters parsed and rates computed from live data.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track uploaded/downloaded data and throughput per interface.",
        epilog="Example: python3 solution.py --interval 2 --count 5 --interface eth0",
    )
    parser.add_argument("-i", "--interface", action="append", default=None,
                        help="interface to monitor (repeatable; default: all)")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="number of sample windows to report (default: 1)")
    parser.add_argument("-s", "--interval", type=float, default=1.0,
                        help="seconds between counter samples (default: 1.0)")
    parser.add_argument("--list", action="store_true",
                        help="list interfaces and cumulative counters, then exit")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    if not PROC_NET_DEV.exists():
        print(f"error: {PROC_NET_DEV} not found; this tool requires Linux procfs",
              file=sys.stderr)
        return 2
    if args.interval <= 0 or args.count <= 0:
        print("error: --interval and --count must be positive", file=sys.stderr)
        return 2

    try:
        snapshot = read_counters()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        for name, item in sorted(snapshot.items()):
            print(f"{name:<12} rx {human_bytes(item.rx_bytes):>10} "
                  f"tx {human_bytes(item.tx_bytes):>10}")
        return 0

    interfaces = args.interface
    if interfaces:
        missing = [name for name in interfaces if name not in snapshot]
        if missing:
            print(f"error: unknown interface(s): {', '.join(missing)}", file=sys.stderr)
            return 2

    session: dict[str, InterfaceTotals] = {}
    previous = snapshot
    last_time = time.monotonic()
    payload: list[dict[str, object]] = []

    for window in range(1, args.count + 1):
        time.sleep(args.interval)
        current = read_counters()
        now = time.monotonic()
        seconds = now - last_time
        totals = collect_totals(previous, current, seconds, interfaces)
        if args.json:
            payload.append({
                "window": window,
                "seconds": round(seconds, 3),
                "interfaces": {
                    name: {
                        "rx_bytes": item.rx_bytes,
                        "tx_bytes": item.tx_bytes,
                        "rx_bytes_per_second": round(item.rx_bytes / item.seconds, 1),
                        "tx_bytes_per_second": round(item.tx_bytes / item.seconds, 1),
                    }
                    for name, item in totals.items()
                },
            })
        else:
            print_report(totals, seconds,
                         f"Bandwidth report - window {window}/{args.count}")
        for name, item in totals.items():
            entry = session.setdefault(name, InterfaceTotals())
            entry.rx_bytes += item.rx_bytes
            entry.tx_bytes += item.tx_bytes
            entry.rx_packets += item.rx_packets
            entry.tx_packets += item.tx_packets
            entry.seconds += item.seconds
        previous = current
        last_time = now

    if args.json:
        print(json.dumps({"windows": payload,
                          "session_totals": {
                              name: {
                                  "rx_bytes": item.rx_bytes,
                                  "tx_bytes": item.tx_bytes,
                              }
                              for name, item in session.items()
                          }}, indent=2))
    elif args.count > 1:
        print_session(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
