#!/usr/bin/env python3
"""Concurrent TCP port scanner.

Connects to every port in a requested range and reports the ones that accept
a TCP connection.  ``--demo`` starts a listener on a free local port and scans
its neighbourhood, so the whole tool can be exercised offline.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

LOCALHOST = "127.0.0.1"


@dataclass(frozen=True)
class PortResult:
    """Outcome of probing one TCP port."""

    port: int
    open: bool
    service: str
    error: str = ""


def parse_ports(spec: str) -> list[int]:
    """Parse a port list such as ``22,80,8000-8100`` into sorted integers."""
    ports: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                first, last = chunk.split("-", 1)
                start, end = int(first), int(last)
            else:
                start = end = int(chunk)
        except ValueError as exc:
            raise ValueError(f"invalid port specification: {chunk!r}") from exc
        if not (1 <= start <= end <= 65535):
            raise ValueError(f"port out of range: {chunk!r} (allowed 1-65535)")
        ports.update(range(start, end + 1))
    if not ports:
        raise ValueError("no ports specified")
    return sorted(ports)


def service_name(port: int) -> str:
    """Best-effort service label from the system services database."""
    try:
        return socket.getservbyport(port, "tcp")
    except OSError:
        return ""


def probe(host: str, port: int, timeout: float) -> PortResult:
    """Attempt a TCP connection to ``host:port``."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortResult(port, True, service_name(port))
    except OSError as exc:
        return PortResult(port, False, service_name(port), type(exc).__name__)


def scan(host: str, ports: list[int], timeout: float, workers: int) -> list[PortResult]:
    """Scan ``ports`` concurrently and return results ordered by port."""
    results: list[PortResult] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(probe, host, port, timeout) for port in ports]
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: item.port)


def resolve(host: str) -> str:
    """Resolve a hostname to its first stream address, supporting IPv6."""
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not infos:
        raise socket.gaierror(f"no addresses found for {host}")
    return str(infos[0][4][0])


def format_results(host: str, results: list[PortResult], elapsed: float) -> str:
    """Render a human-readable scan report."""
    opened = [item for item in results if item.open]
    lines = [f"Scan results for {host}", "-" * 48]
    if opened:
        for item in opened:
            service = f"  ({item.service})" if item.service else ""
            lines.append(f"  OPEN  {item.port:5d}/tcp{service}")
    else:
        lines.append("  No open TCP ports found.")
    lines.append("-" * 48)
    lines.append(f"{len(opened)} open / {len(results)} scanned in {elapsed:.2f}s")
    return "\n".join(lines)


def _accept_loop(listener: socket.socket, stop: threading.Event) -> None:
    """Accept and immediately close connections so the backlog never fills."""
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        conn.close()


def _reserve_demo_ports() -> tuple[socket.socket, int] | None:
    """Open one listener and ensure its next two port numbers are unused."""
    for _ in range(100):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((LOCALHOST, 0))
        listener.listen(16)
        base = listener.getsockname()[1]
        if base + 2 > 65535:
            listener.close()
            continue
        neighbours: list[socket.socket] = []
        for offset in (1, 2):
            spare = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                spare.bind((LOCALHOST, base + offset))
            except OSError:
                spare.close()
                for item in neighbours:
                    item.close()
                break
            neighbours.append(spare)
        else:
            for spare in neighbours:
                spare.close()  # ports stay unused, therefore closed
            return listener, base
        listener.close()
    return None


def run_demo() -> int:
    """Start a local listener and scan a three-port range around it."""
    reserved = _reserve_demo_ports()
    if reserved is None:
        print("demo: unable to reserve local ports", file=sys.stderr)
        return 1
    listener, base = reserved
    stop = threading.Event()
    threading.Thread(target=_accept_loop, args=(listener, stop), daemon=True).start()

    print(f"Demo listener started on {LOCALHOST}:{base}")
    print(f"Scanning {LOCALHOST} ports {base}-{base + 2}\n")
    started = time.perf_counter()
    results = scan(LOCALHOST, parse_ports(f"{base}-{base + 2}"), 0.5, 8)
    elapsed = time.perf_counter() - started
    print(format_results(LOCALHOST, results, elapsed))

    stop.set()
    listener.close()
    expected = {base}
    found = {item.port for item in results if item.open}
    if found != expected:
        print(f"demo: expected open ports {sorted(expected)}, got {sorted(found)}",
              file=sys.stderr)
        return 1
    print("Demo verified: the local listener was the only open port detected.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan a host for open TCP ports.",
        epilog="Example: python3 solution.py 192.168.1.10 -p 1-1024 --timeout 0.3",
    )
    parser.add_argument("target", nargs="?", help="IP address or hostname to scan")
    parser.add_argument("-p", "--ports", default="1-1024",
                        help="ports to scan, e.g. 22,80,8000-8100 (default: 1-1024)")
    parser.add_argument("-t", "--timeout", type=float, default=0.5,
                        help="per-port connect timeout in seconds (default: 0.5)")
    parser.add_argument("-w", "--workers", type=int, default=100,
                        help="concurrent probe workers (default: 100)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.target:
        if not sys.stdin.isatty():
            print("error: provide a target host or use --demo", file=sys.stderr)
            return 2
        try:
            args.target = input("Target IP or hostname: ").strip()
            entered_ports = input(f"Ports [{args.ports}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if entered_ports:
            args.ports = entered_ports
        if not args.target:
            print("error: no target entered", file=sys.stderr)
            return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        ports = parse_ports(args.ports)
        address = resolve(args.target)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except socket.gaierror as exc:
        print(f"error: cannot resolve {args.target}: {exc}", file=sys.stderr)
        return 2

    if not args.json:
        print(f"Scanning {args.target} ({address}) ports {args.ports} "
              f"[timeout {args.timeout}s, {args.workers} workers]")
    started = time.perf_counter()
    results = scan(address, ports, args.timeout, args.workers)
    elapsed = time.perf_counter() - started

    if args.json:
        payload = {
            "target": args.target,
            "address": address,
            "elapsed_seconds": round(elapsed, 3),
            "open_ports": [asdict(item) for item in results if item.open],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_results(args.target, results, elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
