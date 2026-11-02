#!/usr/bin/env python3
"""Website uptime checker with interval or daily-time scheduling.

Performs HTTP(S) checks, prints an on-screen notice when a site is down and can
optionally send an email alert.  ``--demo`` starts a throwaway local web server
plus a deliberately closed port, so both outcomes are shown without internet.
"""

from __future__ import annotations

import argparse
import smtplib
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "site-checker/1.0 (+stdlib)"
LOCALHOST = "127.0.0.1"


@dataclass
class CheckResult:
    """Outcome of a single HTTP check."""

    url: str
    ok: bool
    status: int | None
    latency_ms: float
    error: str | None
    checked_at: str


def normalize_url(url: str) -> str:
    """Add a default scheme when the user omitted one."""
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    return url


def check_site(url: str, timeout: float = 10.0) -> CheckResult:
    """Request ``url`` and classify the response as up or down."""
    url = normalize_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    status: int | None = None
    error: str | None = None
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            response.read(2048)  # touch the body so the request really completes
        ok = 200 <= status < 400
    except HTTPError as exc:
        status = int(exc.code)
        ok = False
        error = f"HTTP {exc.code} {exc.reason}"
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        ok = False
        reason = getattr(exc, "reason", exc)
        error = f"{type(exc).__name__}: {reason}"
    latency = (time.perf_counter() - started) * 1000
    return CheckResult(url, ok, status, latency, error,
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def print_result(result: CheckResult) -> None:
    """Print one check result, with a prominent notice when it is down."""
    if result.ok:
        print(f"[{result.checked_at}] UP    {result.url} "
              f"HTTP {result.status} in {result.latency_ms:.0f} ms")
    else:
        detail = result.error or (f"HTTP {result.status}" if result.status else "no response")
        print(f"[{result.checked_at}] DOWN  {result.url} "
              f"({detail}) after {result.latency_ms:.0f} ms")
        print("  " + "!" * 58)
        print(f"  NOTICE: site is DOWN - {result.url}")
        print("  " + "!" * 58)


def send_email_alert(result: CheckResult, args: argparse.Namespace) -> None:
    """Send a plain-text down alert through the configured SMTP server."""
    message = EmailMessage()
    message["Subject"] = f"[DOWN] {result.url}"
    message["From"] = args.smtp_from or args.email_to
    message["To"] = args.email_to
    message.set_content(
        f"Site check failed.\n\nURL: {result.url}\n"
        f"Checked at: {result.checked_at}\n"
        f"Detail: {result.error or result.status}\n"
    )
    try:
        with smtplib.SMTP(args.smtp_host, args.smtp_port, timeout=10) as smtp:
            if args.smtp_tls:
                smtp.starttls()
            if args.smtp_user:
                import os
                password = os.environ.get("SMTP_PASSWORD", "")
                smtp.login(args.smtp_user, password)
            smtp.send_message(message)
        print(f"  email alert sent to {args.email_to}")
    except (OSError, smtplib.SMTPException) as exc:
        print(f"  email alert failed: {exc}", file=sys.stderr)


def run_check(url: str, timeout: float, args: argparse.Namespace) -> CheckResult:
    """Check one URL and dispatch notifications."""
    result = check_site(url, timeout)
    print_result(result)
    if not result.ok and args.email_to:
        send_email_alert(result, args)
    return result


def parse_times(value: str) -> list[clock_time]:
    """Parse ``HH:MM,HH:MM`` into clock times."""
    times: list[clock_time] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hour, minute = (int(part) for part in chunk.split(":", 1))
            times.append(clock_time(hour, minute))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid time {chunk!r}; expected HH:MM") from exc
    if not times:
        raise ValueError("no times provided")
    return sorted(times)


def next_daily_run(times: Sequence[clock_time], now: datetime | None = None) -> datetime:
    """Return the next datetime matching one of the daily clock times."""
    now = now or datetime.now()
    for moment in times:
        candidate = now.replace(hour=moment.hour, minute=moment.minute,
                                second=0, microsecond=0)
        if candidate > now:
            return candidate
    first = times[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=first.hour, minute=first.minute,
                            second=0, microsecond=0)


def schedule(url: str, args: argparse.Namespace) -> int:
    """Run checks forever (or ``--count`` times) on the requested schedule."""
    completed = 0
    failures = 0
    try:
        while args.count == 0 or completed < args.count:
            if args.at:
                times = parse_times(args.at)
                target = next_daily_run(times)
                wait = max(0.0, (target - datetime.now()).total_seconds())
                print(f"Next check at {target:%Y-%m-%d %H:%M:%S} "
                      f"(sleeping {wait:.0f}s)")
                time.sleep(wait)
            elif completed > 0:
                time.sleep(args.interval)
            result = run_check(url, args.timeout, args)
            completed += 1
            failures += 0 if result.ok else 1
    except KeyboardInterrupt:
        print("\nStopped by user.")
    print(f"\nChecks: {completed}, failures: {failures}")
    return 0 if failures == 0 else 1


class _DemoHandler(BaseHTTPRequestHandler):
    """Serves a fixed 200 response for the local demo server."""

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        body = b"site checker demo: OK\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Silence request logging so demo output stays clean."""


def free_closed_port() -> int:
    """Bind an ephemeral port, close it and return the (now closed) number."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOCALHOST, 0))
        return int(sock.getsockname()[1])


def run_demo() -> int:
    """Check a local web server (up) and a closed local port (down)."""
    server = ThreadingHTTPServer((LOCALHOST, 0), _DemoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Demo web server listening on http://{LOCALHOST}:{port}\n")
    try:
        up = run_check(f"http://{LOCALHOST}:{port}/", 2.0, argparse.Namespace(email_to=None))
        closed = free_closed_port()
        down = run_check(f"http://{LOCALHOST}:{closed}/", 1.0,
                         argparse.Namespace(email_to=None))
    finally:
        server.shutdown()
        server.server_close()

    print(f"\nDemo summary: {int(up.ok)} up, {int(not down.ok)} down.")
    if not up.ok or down.ok:
        print("demo: unexpected check outcome", file=sys.stderr)
        return 1
    print("On-screen notification was raised for the unreachable site.")
    print("Demo complete (no external network used).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether a website is up, on a schedule.",
        epilog="Examples:\n"
               "  python3 solution.py https://example.com --interval 300 --count 0\n"
               "  python3 solution.py https://example.com --at 09:00,18:00",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="URL or hostname to check")
    parser.add_argument("--interval", type=float, default=300.0,
                        help="seconds between checks (default: 300)")
    parser.add_argument("--at", metavar="HH:MM[,HH:MM]",
                        help="daily check times instead of a fixed interval")
    parser.add_argument("--count", type=int, default=1,
                        help="number of checks; 0 means run forever (default: 1)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="HTTP timeout in seconds (default: 10)")
    parser.add_argument("--email-to", help="send down alerts to this address")
    parser.add_argument("--smtp-host", default="localhost",
                        help="SMTP server for alerts (default: localhost)")
    parser.add_argument("--smtp-port", type=int, default=25,
                        help="SMTP port (default: 25)")
    parser.add_argument("--smtp-user", help="SMTP username (password from SMTP_PASSWORD)")
    parser.add_argument("--smtp-from", help="From address for alerts")
    parser.add_argument("--smtp-tls", action="store_true", help="upgrade SMTP with STARTTLS")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.url:
        if not sys.stdin.isatty():
            print("error: provide a URL to check or use --demo", file=sys.stderr)
            return 2
        try:
            args.url = input("URL to check: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.url:
            print("error: no URL entered", file=sys.stderr)
            return 2
    if args.timeout <= 0 or args.interval < 0 or args.count < 0:
        print("error: invalid timeout/interval/count", file=sys.stderr)
        return 2
    try:
        if args.at:
            parse_times(args.at)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return schedule(normalize_url(args.url), args)


if __name__ == "__main__":
    raise SystemExit(main())
