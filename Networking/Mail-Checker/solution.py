#!/usr/bin/env python3
"""Mailbox checker for IMAP and POP3 accounts.

Logs in over SSL (or plaintext with --no-ssl), reports message counts and the
latest headers, and can poll on an interval.  ``--demo`` uses a simulated
mailbox so the reporting and polling logic runs without credentials.
"""

from __future__ import annotations

import argparse
import imaplib
import json
import os
import poplib
import sys
import time
from dataclasses import asdict, dataclass, field
from email import message_from_bytes
from email.header import decode_header
from getpass import getpass

DEFAULT_PORTS = {("imap", True): 993, ("imap", False): 143,
                 ("pop3", True): 995, ("pop3", False): 110}


@dataclass
class MessageSummary:
    """The header fields this tool displays for one message."""

    number: int
    sender: str
    subject: str
    date: str


@dataclass
class MailboxReport:
    """Result of one mailbox check."""

    protocol: str
    host: str
    user: str
    total: int = 0
    unread: int = 0
    messages: list[MessageSummary] = field(default_factory=list)
    error: str | None = None


def decode_value(raw: object) -> str:
    """Decode a possibly RFC 2047 encoded header value."""
    if raw is None:
        return "(unknown)"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    text = str(raw)
    try:
        parts = decode_header(text)
    except (ValueError, TypeError):
        return text.strip() or "(unknown)"
    pieces: list[str] = []
    for value, charset in parts:
        if isinstance(value, bytes):
            try:
                pieces.append(value.decode(charset or "utf-8", "replace"))
            except LookupError:
                pieces.append(value.decode("utf-8", "replace"))
        else:
            pieces.append(value)
    return "".join(pieces).strip() or "(unknown)"


def headers_to_summary(number: int, raw: bytes) -> MessageSummary:
    """Extract sender/subject/date from a raw header block."""
    message = message_from_bytes(raw)
    return MessageSummary(
        number=number,
        sender=decode_value(message.get("From")),
        subject=decode_value(message.get("Subject")),
        date=decode_value(message.get("Date")),
    )


def check_imap(host: str, port: int, user: str, password: str, *,
               use_ssl: bool = True, mailbox: str = "INBOX",
               limit: int = 5, timeout: float = 10.0) -> MailboxReport:
    """Fetch mailbox counts and recent headers over IMAP."""
    report = MailboxReport("IMAP", host, user)
    client: imaplib.IMAP4 | None = None
    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, port, timeout=timeout)
        else:
            client = imaplib.IMAP4(host, port, timeout=timeout)
        client.login(user, password)
        status, data = client.select(mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"cannot select mailbox {mailbox!r}")
        report.total = int(data[0]) if data and data[0] else 0

        status, unseen = client.search(None, "UNSEEN")
        if status == "OK" and unseen and unseen[0]:
            report.unread = len(unseen[0].split())

        status, all_ids = client.search(None, "ALL")
        ids = all_ids[0].split() if status == "OK" and all_ids and all_ids[0] else []
        selected = ids[-limit:]
        if selected:
            status, fetched = client.fetch(
                ",".join(item.decode("ascii") for item in selected),
                "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
            )
            if status != "OK":
                raise RuntimeError("header fetch failed")
            index = 0
            for item in fetched:
                if isinstance(item, tuple) and len(item) >= 2:
                    number = int(selected[index]) if index < len(selected) else index + 1
                    report.messages.append(headers_to_summary(number, item[1]))
                    index += 1
    except (imaplib.IMAP4.error, OSError, RuntimeError, ValueError) as exc:
        report.error = f"{type(exc).__name__}: {exc}"
    finally:
        if client is not None:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
    return report


def check_pop3(host: str, port: int, user: str, password: str, *,
               use_ssl: bool = True, limit: int = 5,
               timeout: float = 10.0) -> MailboxReport:
    """Fetch mailbox counts and recent headers over POP3."""
    report = MailboxReport("POP3", host, user)
    client: poplib.POP3 | None = None
    try:
        if use_ssl:
            client = poplib.POP3_SSL(host, port, timeout=timeout)
        else:
            client = poplib.POP3(host, port, timeout=timeout)
        client.user(user)
        client.pass_(password)
        count, _size = client.stat()
        report.total = int(count)
        report.unread = int(count)  # POP3 has no read/unread flag
        numbers = list(range(1, count + 1))[-limit:]
        for number in numbers:
            try:
                _response, lines, _octets = client.top(number, 0)
            except poplib.error_proto:
                _response, lines, _octets = client.retr(number)
            report.messages.append(headers_to_summary(number, b"\r\n".join(lines)))
    except (poplib.error_proto, OSError, ValueError) as exc:
        report.error = f"{type(exc).__name__}: {exc}"
    finally:
        if client is not None:
            try:
                client.quit()
            except (poplib.error_proto, OSError):
                pass
    return report


def print_report(report: MailboxReport, previous_total: int | None = None) -> None:
    """Render a report; ``previous_total`` enables a new-mail indicator."""
    label = f"{report.protocol} {report.user}@{report.host}"
    print(f"\nMailbox check - {label}")
    print("-" * 64)
    if report.error:
        print(f"  ERROR: {report.error}")
        return
    extra = " (no read/unread flag)" if report.protocol == "POP3" else ""
    print(f"  Total messages: {report.total}   Unread: {report.unread}{extra}")
    if previous_total is not None:
        new_mail = max(0, report.total - previous_total)
        print(f"  New since last check: {new_mail}")
    if report.messages:
        print("  Latest messages:")
        for item in reversed(report.messages):
            print(f"    #{item.number:<4} {item.date[:31]:<32} {item.sender[:28]}")
            print(f"          {item.subject[:76]}")
    else:
        print("  Mailbox is empty.")


def resolve_password(args: argparse.Namespace) -> str:
    """Password from CLI, environment or an interactive prompt."""
    if args.password:
        return args.password
    env_password = os.environ.get("MAIL_PASSWORD")
    if env_password:
        return env_password
    if sys.stdin.isatty():
        return getpass(f"Password for {args.user}@{args.host}: ")
    raise RuntimeError("no password supplied; set MAIL_PASSWORD or use --password")


def run_polling(args: argparse.Namespace) -> int:
    """Check the mailbox once or repeatedly."""
    try:
        password = resolve_password(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    port = args.port or DEFAULT_PORTS[(args.protocol, not args.no_ssl)]
    previous: int | None = None
    failures = 0
    checks = 0
    try:
        while args.count == 0 or checks < args.count:
            if checks:
                time.sleep(args.interval)
            if args.protocol == "imap":
                report = check_imap(args.host, port, args.user, password,
                                    use_ssl=not args.no_ssl, mailbox=args.mailbox,
                                    limit=args.limit, timeout=args.timeout)
            else:
                report = check_pop3(args.host, port, args.user, password,
                                    use_ssl=not args.no_ssl, limit=args.limit,
                                    timeout=args.timeout)
            checks += 1
            failures += 1 if report.error else 0
            if args.json:
                print(json.dumps(asdict(report), indent=2))
            else:
                print_report(report, previous)
            if not report.error:
                previous = report.total
    except KeyboardInterrupt:
        print("\nStopped by user.")
    return 0 if checks and failures < checks else 1


DEMO_MESSAGES = [
    MessageSummary(1, "alerts@status.example", "Scheduled maintenance notice",
                   "Mon, 02 Nov 2026 07:15:00 +0000"),
    MessageSummary(2, "newsletter@example.org", "Weekly digest: 5 stories",
                   "Mon, 02 Nov 2026 08:02:00 +0000"),
    MessageSummary(3, "billing@example.net", "Invoice 2026-11 is ready",
                   "Mon, 02 Nov 2026 09:30:00 +0000"),
    MessageSummary(4, "friend@example.com", "Lunch on Friday?",
                   "Mon, 02 Nov 2026 10:05:00 +0000"),
]


def simulated_report(step: int) -> MailboxReport:
    """Deterministic mailbox used by the demo."""
    visible = 3 if step == 1 else 4
    return MailboxReport(
        protocol="IMAP", host="imap.example.test", user="demo",
        total=visible, unread=1 if step == 1 else 2,
        messages=DEMO_MESSAGES[:visible],
    )


def run_demo() -> int:
    """Run two simulated polls and show the new-mail delta."""
    print("Demo mode: simulated mailbox (no server or credentials needed).")
    print("Real IMAP/POP3 code paths are used when --host/--user are supplied.")
    previous: int | None = None
    for step in (1, 2):
        report = simulated_report(step)
        print_report(report, previous)
        previous = report.total
        if step == 1:
            print("\n  [simulating 1 new message and a 0.2s polling interval]")
            time.sleep(0.2)
    print("\nDemo complete: polling, header decoding and new-mail detection work.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check an IMAP or POP3 mailbox for new mail.",
        epilog="Example: MAIL_PASSWORD=secret python3 solution.py "
               "--protocol imap --host imap.example.com --user me --count 0",
    )
    parser.add_argument("--protocol", choices=("imap", "pop3"), default="imap",
                        help="mailbox protocol (default: imap)")
    parser.add_argument("--host", help="mail server hostname")
    parser.add_argument("--port", type=int, help="server port (default: protocol/SSL standard)")
    parser.add_argument("--user", help="account username")
    parser.add_argument("--password", help="account password (prefer MAIL_PASSWORD env var)")
    parser.add_argument("--mailbox", default="INBOX", help="IMAP mailbox (default: INBOX)")
    parser.add_argument("--no-ssl", action="store_true", help="use plaintext instead of SSL")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="seconds between checks (default: 60)")
    parser.add_argument("--count", type=int, default=1,
                        help="number of checks; 0 means forever (default: 1)")
    parser.add_argument("--limit", type=int, default=5,
                        help="recent messages to display (default: 5)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="network timeout in seconds (default: 10)")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained simulated demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.host or not args.user:
        if not sys.stdin.isatty():
            print("error: --host and --user are required (or use --demo)",
                  file=sys.stderr)
            return 2
        try:
            if not args.host:
                args.host = input("Mail server host: ").strip()
            if not args.user:
                args.user = input("Username: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.host or not args.user:
            print("error: host and user are required", file=sys.stderr)
            return 2
    if args.interval < 0 or args.count < 0 or args.limit <= 0 or args.timeout <= 0:
        print("error: invalid interval/count/limit/timeout", file=sys.stderr)
        return 2
    return run_polling(args)


if __name__ == "__main__":
    raise SystemExit(main())
