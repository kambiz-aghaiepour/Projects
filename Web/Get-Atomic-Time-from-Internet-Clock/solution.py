#!/usr/bin/env python3
"""Get Atomic Time from Internet Clock - SNTP client with HTTP fallback.

Queries an NTP/SNTP server over UDP (port 123 by default), computes the offset
between the local clock and the server's clock using the standard four-timestamp
formula, and prints the corrected UTC time.  If UDP is blocked, a JSON HTTP time
service is used as a fallback.  ``--demo`` runs a simulated SNTP server on a
loopback port and also demonstrates the graceful "network unavailable" path.
"""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import struct
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NTP_EPOCH_DELTA = 2_208_988_800  # seconds from 1900-01-01 to 1970-01-01
NTP_PORT = 123
DEFAULT_SERVER = "pool.ntp.org"
HTTP_ENDPOINTS = (
    "https://worldtimeapi.org/api/timezone/Etc/UTC",
    "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
)
USER_AGENT = "atomic-time/1.0 (+stdlib)"


class TimeError(Exception):
    """Raised when a time source cannot be queried or parsed."""


@dataclass
class TimeSample:
    """A clock comparison against one remote source."""

    source: str
    offset: float          # server clock - local clock, seconds
    round_trip: float      # seconds
    server_time: float     # best estimate of the server's Unix time
    detail: str = ""


def ntp_to_bytes(timestamp: float) -> bytes:
    """Encode a Unix timestamp as a 64-bit NTP timestamp."""
    seconds = int(timestamp) + NTP_EPOCH_DELTA
    fraction = int((timestamp % 1.0) * (1 << 32)) & 0xFFFFFFFF
    return struct.pack("!II", seconds & 0xFFFFFFFF, fraction)


def ntp_from_bytes(data: bytes) -> float:
    """Decode a 64-bit NTP timestamp into Unix seconds (NTP era 0/1 safe)."""
    seconds, fraction = struct.unpack("!II", data)
    seconds -= NTP_EPOCH_DELTA
    # Treat values before 1968 as the post-2036 era.
    if seconds < -31_536_000:
        seconds += 1 << 32
    return seconds + fraction / (1 << 32)


def query_sntp(server: str, port: int = NTP_PORT, timeout: float = 3.0) -> TimeSample:
    """Send one SNTP request and derive the clock offset."""
    packet = bytearray(48)
    packet[0] = 0x23  # LI=0, version 4, mode 3 (client)
    t1 = time.time()
    packet[40:48] = ntp_to_bytes(t1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (server, port))
            data, _address = sock.recvfrom(1024)
            t4 = time.time()
    except socket.timeout as exc:
        raise TimeError(f"SNTP request to {server}:{port} timed out after {timeout:g}s") from exc
    except OSError as exc:
        raise TimeError(f"SNTP request to {server}:{port} failed: {exc}") from exc

    if len(data) < 48:
        raise TimeError(f"short SNTP reply ({len(data)} bytes)")
    mode = data[0] & 0x07
    if mode != 4:
        raise TimeError(f"unexpected SNTP mode {mode} (expected server mode 4)")
    stratum = data[1]
    if stratum == 0:
        raise TimeError("SNTP server returned a kiss-o'-death packet")
    if stratum > 15:
        raise TimeError(f"SNTP server is unsynchronised (stratum {stratum})")
    if data[24:32] != packet[40:48]:
        raise TimeError("SNTP originate timestamp does not match the request")

    t2 = ntp_from_bytes(data[32:40])  # server receive time
    t3 = ntp_from_bytes(data[40:48])  # server transmit time
    offset = ((t2 - t1) + (t3 - t4)) / 2.0
    round_trip = (t4 - t1) - (t3 - t2)
    server_time = t4 + offset
    return TimeSample(f"SNTP {server}:{port}", offset, max(0.0, round_trip),
                      server_time, f"stratum {stratum}")


def _parse_iso(value: str) -> float:
    """Parse an ISO-8601 timestamp, accepting a trailing ``Z``."""
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise TimeError(f"cannot parse timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def query_http(url: str, timeout: float = 5.0) -> TimeSample:
    """Fetch the time from a JSON HTTP endpoint and compute the offset."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    started = time.time()
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(65536)
        finished = time.time()
    except HTTPError as exc:
        raise TimeError(f"HTTP {exc.code} from {url}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise TimeError(f"HTTP time request to {url} failed: {getattr(exc, 'reason', exc)}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimeError(f"invalid JSON from {url}") from exc
    if not isinstance(payload, dict):
        raise TimeError(f"unexpected JSON payload from {url}")

    server_epoch: float | None = None
    detail = "HTTP JSON"
    if isinstance(payload.get("utc_datetime"), str):
        server_epoch = _parse_iso(payload["utc_datetime"])
        detail = "HTTP utc_datetime"
    elif isinstance(payload.get("datetime"), str):
        server_epoch = _parse_iso(payload["datetime"])
        detail = "HTTP datetime"
    elif isinstance(payload.get("dateTime"), str):
        server_epoch = _parse_iso(payload["dateTime"])
        detail = "HTTP dateTime"
    elif isinstance(payload.get("unixtime"), (int, float)):
        server_epoch = float(payload["unixtime"])
        detail = "HTTP unixtime (1 s resolution)"
    if server_epoch is None:
        raise TimeError(f"no recognised time field in response from {url}")

    midpoint = (started + finished) / 2.0
    return TimeSample(url, server_epoch - midpoint, finished - started,
                      server_epoch, detail)


def choose_source(args: argparse.Namespace) -> TimeSample:
    """Try SNTP (median of samples), then HTTP unless disabled."""
    errors: list[str] = []
    if args.source in ("auto", "sntp"):
        samples: list[TimeSample] = []
        for _ in range(max(1, args.samples)):
            try:
                samples.append(query_sntp(args.server, args.port, args.timeout))
            except TimeError as exc:
                errors.append(str(exc))
                break
        if samples:
            offsets = [sample.offset for sample in samples]
            median = statistics.median(offsets)
            best = min(samples, key=lambda sample: sample.round_trip)
            return TimeSample(best.source, median, best.round_trip,
                              time.time() + median, f"{len(samples)} sample(s), median offset")
        if args.source == "sntp":
            raise TimeError(errors[-1] if errors else "SNTP query failed")

    if args.source in ("auto", "http"):
        endpoints = ([args.http_url] if args.http_url else []) + list(HTTP_ENDPOINTS)
        for url in endpoints:
            try:
                return query_http(url, args.http_timeout)
            except TimeError as exc:
                errors.append(str(exc))
        raise TimeError(errors[-1] if errors else "no HTTP time endpoint configured")
    raise TimeError("no time source selected")


def format_utc(epoch: float) -> str:
    """Format a Unix timestamp as millisecond-precision UTC."""
    stamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return stamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"


def describe_offset(offset: float) -> str:
    """Sentence describing which clock is ahead."""
    if abs(offset) < 0.0005:
        return "clocks agree within 0.5 ms"
    if offset > 0:
        return f"server is ahead by {offset:.3f} s"
    return f"server is behind by {abs(offset):.3f} s"


def print_sample(sample: TimeSample, show_detail: bool = True) -> None:
    """Print a human-readable time report."""
    corrected = time.time() + sample.offset
    print(f"Source:        {sample.source}")
    if show_detail and sample.detail:
        print(f"Detail:        {sample.detail}")
    print(f"Round trip:    {sample.round_trip * 1000:.1f} ms")
    print(f"Clock offset:  {sample.offset:+.4f} s ({describe_offset(sample.offset)})")
    print(f"Local UTC:     {format_utc(time.time())}")
    print(f"Corrected UTC: {format_utc(corrected)}")
    accuracy = sample.round_trip / 2.0
    print(f"Uncertainty:   about ±{accuracy * 1000:.1f} ms (half the round trip)")


def sample_to_dict(sample: TimeSample) -> dict[str, Any]:
    """Serialise a sample for ``--json``."""
    return {
        "source": sample.source,
        "offset_seconds": round(sample.offset, 6),
        "round_trip_seconds": round(sample.round_trip, 6),
        "server_utc": format_utc(sample.server_time),
        "local_utc": format_utc(time.time()),
        "corrected_utc": format_utc(time.time() + sample.offset),
        "detail": sample.detail,
    }


# --------------------------------------------------------------------------- demo

class FakeSntpServer(threading.Thread):
    """A tiny SNTP responder whose clock is ``offset`` seconds ahead."""

    def __init__(self, offset: float) -> None:
        super().__init__(daemon=True)
        self.offset = offset
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                data, address = self._sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) < 48:
                continue
            now = time.time() + self.offset
            reply = bytearray(data[:48])
            reply[0] = 0x24  # LI=0, version 4, mode 4 (server)
            reply[1] = 1     # stratum 1
            reply[2] = 6     # poll interval
            reply[3] = 0xEC  # precision 2^-20
            reply[4:12] = b"\x00" * 8
            reply[12:16] = b"LOCL"
            reply[16:24] = ntp_to_bytes(now - 60)
            reply[24:32] = data[40:48]
            reply[32:40] = ntp_to_bytes(now)
            reply[40:48] = ntp_to_bytes(now + 0.0005)
            try:
                self._sock.sendto(reply, address)
            except OSError:
                break

    def stop(self) -> None:
        """Stop the responder and close its socket."""
        self._stop.set()
        self.join(timeout=1.0)
        self._sock.close()


def closed_udp_port() -> int:
    """Bind an ephemeral UDP port, close it, and return the (now closed) port."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_demo() -> int:
    """Simulate an SNTP server and demonstrate the offline fallback."""
    print("Atomic Time demo (offline: one simulated SNTP server, then a failure path)\n")
    fake = FakeSntpServer(offset=1.75)
    fake.start()
    print(f"1. Simulated SNTP server on 127.0.0.1:{fake.port} with a +1.750 s clock")
    good = False
    try:
        samples = [query_sntp("127.0.0.1", fake.port, timeout=2.0) for _ in range(3)]
        median = statistics.median(sample.offset for sample in samples)
        for index, sample in enumerate(samples, 1):
            print(f"   sample {index}: offset {sample.offset:+.4f} s, "
                  f"round trip {sample.round_trip * 1000:.2f} ms")
        print()
        print_sample(TimeSample(f"SNTP 127.0.0.1:{fake.port}", median,
                                min(s.round_trip for s in samples),
                                time.time() + median,
                                f"{len(samples)} samples, median offset"))
        good = abs(median - 1.75) < 0.05
    finally:
        fake.stop()

    print("\n2. Simulated network outage (closed UDP port, 0.4 s timeout)")
    dead_port = closed_udp_port()
    try:
        query_sntp("127.0.0.1", dead_port, timeout=0.4)
        print("   unexpected: a reply arrived on a closed port")
        good = False
    except TimeError as exc:
        print(f"   SNTP unavailable: {exc}")
    print("   HTTP fallback skipped in this offline demo.")
    print(f"   Showing local clock instead: {format_utc(time.time())}")
    print("   Without a reachable time source only the local clock is available;")
    print("   rerun without --demo and with network access to obtain a correction.")

    print(f"\nDemo complete: simulated offset {'verified' if good else 'FAILED'}, "
          f"offline path handled gracefully.")
    return 0 if good else 1


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Get the true time from an Internet clock (SNTP, HTTP fallback).",
        epilog="Examples:\n"
               "  python3 solution.py\n"
               "  python3 solution.py --server time.cloudflare.com --samples 5\n"
               "  python3 solution.py --source http --json\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--server", default=DEFAULT_SERVER,
                        help=f"NTP/SNTP server hostname (default: {DEFAULT_SERVER})")
    parser.add_argument("--port", type=int, default=NTP_PORT,
                        help=f"SNTP UDP port (default: {NTP_PORT})")
    parser.add_argument("--timeout", type=float, default=3.0,
                        help="per-request UDP timeout in seconds (default: 3)")
    parser.add_argument("--samples", type=int, default=3,
                        help="SNTP samples, median offset is used (default: 3)")
    parser.add_argument("--source", choices=("auto", "sntp", "http"), default="auto",
                        help="time source; auto tries SNTP then HTTP (default: auto)")
    parser.add_argument("--http-url", help="custom JSON HTTP time endpoint")
    parser.add_argument("--http-timeout", type=float, default=5.0,
                        help="HTTP fallback timeout in seconds (default: 5)")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not 0 < args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.timeout <= 0 or args.http_timeout <= 0:
        parser.error("timeouts must be positive")
    if args.samples < 1:
        parser.error("--samples must be at least 1")

    if not args.json:
        print(f"Querying {args.server}:{args.port} (source: {args.source})...")
    try:
        sample = choose_source(args)
    except TimeError as exc:
        print(f"error: could not obtain network time: {exc}", file=sys.stderr)
        print(f"local clock reads {format_utc(time.time())}; no correction applied.",
              file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(sample_to_dict(sample), indent=2))
    else:
        print_sample(sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
