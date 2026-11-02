#!/usr/bin/env python3
"""WHOIS lookup client for domains and IP addresses.

Queries port 43 directly, follows one referral (IANA -> registry, ARIN -> RIR),
and extracts the commonly useful fields.  ``--demo`` parses bundled WHOIS
snapshots, so it works with no network access.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

WHOIS_PORT = 43
MAX_RESPONSE = 2_000_000
SAMPLE_DIR = Path(__file__).resolve().parent / "samples"
REFERRAL_RE = re.compile(
    r"^\s*(?:ReferralServer|refer)\s*:\s*(?:whois://)?([A-Za-z0-9.-]+)(?::(\d+))?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "Registrar": ("Registrar", "Sponsoring Registrar", "Registrar Name"),
    "Creation Date": ("Creation Date", "Created On", "created", "RegDate"),
    "Updated Date": ("Updated Date", "Last Updated", "last-modified", "Updated"),
    "Expiry Date": ("Registry Expiry Date", "Registrar Registration Expiration Date",
                    "Expiration Date", "paid-till"),
    "Organisation": ("OrgName", "Organisation", "Organization", "org-name", "owner"),
    "Country": ("Country", "country"),
    "NetRange": ("NetRange", "inetnum"),
    "CIDR": ("CIDR",),
    "Abuse Email": ("OrgAbuseEmail", "abuse-mailbox", "Abuse Email"),
}
NAME_SERVER_RE = re.compile(r"^\s*(?:Name Server|nserver)\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
STATUS_RE = re.compile(r"^\s*(?:Domain Status|status)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
TLD_SERVERS = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "info": "whois.afilias.net",
    "io": "whois.nic.io",
    "dev": "whois.nic.google",
    "app": "whois.nic.google",
    "uk": "whois.nic.uk",
    "de": "whois.denic.de",
    "fr": "whois.nic.fr",
    "nl": "whois.domain-registry.nl",
    "ca": "whois.cira.ca",
    "au": "whois.auda.org.au",
    "jp": "whois.jprs.jp",
}


@dataclass
class WhoisStep:
    """One server query and its raw response."""

    server: str
    text: str


@dataclass
class WhoisResult:
    """Parsed WHOIS answer plus the raw query trail."""

    query: str
    kind: str
    steps: list[WhoisStep] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    name_servers: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.steps[-1].text if self.steps else ""


def normalize_query(value: str) -> str:
    """Strip URL noise and validate that this is a domain or IP literal."""
    query = value.strip()
    if "://" in query:
        query = query.split("://", 1)[1]
    query = query.split("/", 1)[0].split("?", 1)[0].strip(".")
    if not query:
        raise ValueError("empty query")
    try:
        return str(ipaddress.ip_address(query))
    except ValueError:
        pass
    if len(query) > 253 or "." not in query:
        raise ValueError(f"not a domain name or IP address: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", query) or ".." in query:
        raise ValueError(f"invalid domain name: {value!r}")
    return query.lower()


def query_kind(query: str) -> str:
    """Return ``ipv4``, ``ipv6`` or ``domain``."""
    try:
        address = ipaddress.ip_address(query)
    except ValueError:
        return "domain"
    return "ipv4" if address.version == 4 else "ipv6"


def query_server(server: str, query: str, port: int = WHOIS_PORT,
                 timeout: float = 10.0) -> str:
    """Send a WHOIS query over TCP and return the decoded response."""
    try:
        with socket.create_connection((server, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            if query.isascii():
                wire = query.encode("ascii") + b"\r\n"
            else:
                wire = query.encode("idna") + b"\r\n"
            sock.sendall(wire)
            chunks: list[bytes] = []
            received = 0
            while received < MAX_RESPONSE:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
                received += len(data)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        raise RuntimeError(f"cannot query {server}: {exc}") from exc
    return b"".join(chunks).decode("utf-8", "replace")


def parse_referral(text: str) -> tuple[str, int] | None:
    """Extract a referral host/port from a WHOIS response."""
    match = REFERRAL_RE.search(text)
    if not match:
        return None
    host = match.group(1).lower()
    port = int(match.group(2) or WHOIS_PORT)
    return host, port


def parse_fields(text: str) -> dict[str, str]:
    """Extract the first value for each recognised field."""
    fields: dict[str, str] = {}
    for label, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            match = re.search(rf"^\s*{re.escape(alias)}\s*:\s*(.+?)\s*$",
                              text, re.IGNORECASE | re.MULTILINE)
            if match:
                fields[label] = match.group(1).strip()
                break
    return fields


def parse_result(query: str, steps: list[WhoisStep]) -> WhoisResult:
    """Build a parsed result from the final response in the trail."""
    text = steps[-1].text if steps else ""
    return WhoisResult(
        query=query,
        kind=query_kind(query),
        steps=steps,
        fields=parse_fields(text),
        name_servers=[item.rstrip(".") for item in NAME_SERVER_RE.findall(text)],
        statuses=[item.strip() for item in STATUS_RE.findall(text)],
    )


def lookup(query: str, server: str | None = None, follow: bool = True,
           timeout: float = 10.0) -> WhoisResult:
    """Run a WHOIS lookup, optionally following one referral."""
    normalized = normalize_query(query)
    kind = query_kind(normalized)
    steps: list[WhoisStep] = []
    if server:
        text = query_server(server, normalized, timeout=timeout)
        steps.append(WhoisStep(server, text))
    else:
        first = "whois.arin.net" if kind in ("ipv4", "ipv6") else "whois.iana.org"
        text = query_server(first, normalized, timeout=timeout)
        steps.append(WhoisStep(first, text))
        if follow:
            referral = parse_referral(text)
            target: tuple[str, int] | None = None
            if referral and referral[0] != first:
                target = referral
            elif kind == "domain":
                fallback = TLD_SERVERS.get(normalized.rsplit(".", 1)[-1])
                if fallback and fallback != first:
                    target = (fallback, WHOIS_PORT)
            if target:
                host, port = target
                try:
                    referred_text = query_server(host, normalized, port, timeout)
                except RuntimeError as exc:
                    print(f"warning: referral to {host} failed: {exc}", file=sys.stderr)
                else:
                    steps.append(WhoisStep(host, referred_text))
    return parse_result(normalized, steps)


def print_summary(result: WhoisResult) -> None:
    """Print the parsed highlights of a lookup."""
    print(f"Query: {result.query} ({result.kind})")
    if not result.fields and not result.name_servers:
        print("  No recognised fields in the response; run without --summary for the full text.")
        return
    for label, value in result.fields.items():
        print(f"  {label:<15} {value}")
    if result.name_servers:
        print(f"  {'Name servers':<15} {', '.join(result.name_servers)}")
    if result.statuses:
        print(f"  {'Status':<15} {'; '.join(result.statuses)}")


def run_demo() -> int:
    """Parse the bundled example.com and 8.8.8.8 snapshots."""
    print("Demo mode: bundled WHOIS snapshots (no network queries).\n")
    samples = [
        ("example.com", "example_com.txt"),
        ("8.8.8.8", "8_8_8_8.txt"),
    ]
    for query, filename in samples:
        path = SAMPLE_DIR / filename
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"demo: missing sample {filename}: {exc}", file=sys.stderr)
            return 1
        result = parse_result(query, [WhoisStep("sample.local", text)])
        print_summary(result)
        print()
    print("Demo complete: WHOIS field extraction verified on bundled snapshots.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Look up domain or IP registration data via WHOIS.",
        epilog="Examples:\n"
               "  python3 solution.py example.com\n"
               "  python3 solution.py 8.8.8.8 --summary\n"
               "  python3 solution.py example.com --server whois.verisign-grs.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="domain name or IP address")
    parser.add_argument("--server", help="query this WHOIS server instead of auto-selecting")
    parser.add_argument("--no-follow", action="store_true",
                        help="do not follow the registry referral")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="socket timeout in seconds (default: 10)")
    parser.add_argument("--summary", action="store_true",
                        help="show parsed fields instead of the full response")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.query:
        if not sys.stdin.isatty():
            print("error: provide a domain or IP address, or use --demo",
                  file=sys.stderr)
            return 2
        try:
            args.query = input("Domain or IP address: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.query:
            print("error: no query entered", file=sys.stderr)
            return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        result = lookup(args.query, args.server, not args.no_follow, args.timeout)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
        return 0
    if args.summary:
        print_summary(result)
        return 0
    for step in result.steps:
        print(f"--- WHOIS server: {step.server} ---")
        print(step.text.strip())
        print()
    print("--- Parsed summary ---")
    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
