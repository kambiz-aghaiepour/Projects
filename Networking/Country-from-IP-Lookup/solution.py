#!/usr/bin/env python3
"""Country lookup for IP addresses, with offline handling of non-public ranges.

Private, loopback, link-local, reserved and documentation addresses are
classified locally.  Globally routable addresses are sent to the ipwho.is API
over HTTPS with a timeout; failures are reported cleanly instead of crashing.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://ipwho.is"
USER_AGENT = "country-from-ip/1.0 (+stdlib)"

SPECIAL_NETWORKS: list[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str]] = [
    (ipaddress.ip_network("100.64.0.0/10"), "carrier-grade NAT (RFC 6598)"),
    (ipaddress.ip_network("192.0.2.0/24"), "documentation network (TEST-NET-1)"),
    (ipaddress.ip_network("198.51.100.0/24"), "documentation network (TEST-NET-2)"),
    (ipaddress.ip_network("203.0.113.0/24"), "documentation network (TEST-NET-3)"),
    (ipaddress.ip_network("198.18.0.0/15"), "benchmarking network (RFC 2544)"),
    (ipaddress.ip_network("2001:db8::/32"), "documentation network (RFC 3849)"),
]


@dataclass
class LookupResult:
    """Everything known about one queried address."""

    ip: str
    category: str
    detail: str
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    org: str | None = None
    error: str | None = None


def classify(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[str, str]:
    """Classify an address without any network access."""
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if address.is_loopback:
        return "loopback", "loopback address (this host)"
    if address.is_unspecified:
        return "unspecified", "unspecified address (0.0.0.0 / ::)"
    if address.is_link_local:
        return "link-local", "link-local address (not routable)"
    if address.is_multicast:
        return "multicast", "multicast group address"
    for network, label in SPECIAL_NETWORKS:
        if address.version == network.version and address in network:
            return "reserved", label
    if address.is_private:
        if isinstance(address, ipaddress.IPv4Address):
            return "private", "private network (RFC 1918, not routable)"
        return "private", "unique-local IPv6 address (RFC 4193)"
    if address.is_reserved:
        return "reserved", "reserved by IANA"
    if not address.is_global:
        return "non-public", "not globally routable"
    return "public", "globally routable address"


def parse_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Parse an IP literal, raising ValueError with a friendly message."""
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"not a valid IP address: {value!r}") from exc


def _fetch_json(url: str, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT,
                                    "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read(1_000_000).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("API returned an unexpected payload")
    return payload


def lookup_public(ip: str | None, timeout: float = 5.0) -> LookupResult:
    """Query ipwho.is for a public address (or the caller's address if None)."""
    url = f"{API_ROOT}/{ip}" if ip else f"{API_ROOT}/"
    try:
        payload = _fetch_json(url, timeout)
        if payload.get("success") is False:
            message = payload.get("message") or "lookup rejected by API"
            raise ValueError(str(message))
        resolved = str(payload.get("ip") or ip or "unknown")
        connection = payload.get("connection") or {}
        timezone = payload.get("timezone") or {}
        org = connection.get("org") if isinstance(connection, dict) else None
        tz_id = timezone.get("id") if isinstance(timezone, dict) else None
        detail_parts = [str(payload.get("type") or "public address").upper()]
        if tz_id:
            detail_parts.append(f"timezone {tz_id}")
        return LookupResult(
            ip=resolved,
            category="public",
            detail=", ".join(detail_parts),
            country=str(payload.get("country") or "") or None,
            country_code=str(payload.get("country_code") or "") or None,
            region=str(payload.get("region") or "") or None,
            city=str(payload.get("city") or "") or None,
            org=str(org) if org else None,
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return LookupResult(ip=ip or "unknown", category="public",
                            detail="lookup attempted", error=str(reason))


def describe(result: LookupResult) -> str:
    """One-line human-readable description of a lookup result."""
    if result.error:
        return f"{result.ip:<16} {result.category:<12} lookup unavailable: {result.error}"
    if result.category != "public":
        return f"{result.ip:<16} {result.category:<12} {result.detail}"
    place = ", ".join(part for part in (result.city, result.region, result.country) if part)
    code = f" ({result.country_code})" if result.country_code else ""
    org = f" - {result.org}" if result.org else ""
    return f"{result.ip:<16} public       {place or 'unknown location'}{code}{org}"


def gather_targets(values: Iterable[str], files: Iterable[str]) -> list[str]:
    """Combine positional IPs and file contents, preserving order and deduping."""
    targets: list[str] = []
    for value in values:
        targets.append(value)
    for name in files:
        try:
            with open(name, encoding="utf-8") as handle:
                for line in handle:
                    line = line.split("#", 1)[0].strip()
                    if line:
                        targets.append(line)
        except OSError as exc:
            raise ValueError(f"cannot read {name}: {exc}") from exc
    seen: set[str] = set()
    unique: list[str] = []
    for item in targets:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find the country an IP address is registered in.",
        epilog="Example: python3 solution.py 8.8.8.8 1.1.1.1 --timeout 3",
    )
    parser.add_argument("ips", nargs="*", help="IP addresses to look up")
    parser.add_argument("-f", "--file", action="append", default=[],
                        help="read addresses from a file (one per line, repeatable)")
    parser.add_argument("--me", action="store_true",
                        help="look up the public IP of this machine")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="API timeout in seconds (default: 5)")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained demonstration")
    return parser


def run_demo() -> int:
    """Classify non-public addresses offline and try one public lookup."""
    print("Demo: offline classification of private and special-use addresses\n")
    demo_ips = ["10.0.0.5", "192.168.1.10", "127.0.0.1",
                "169.254.10.20", "203.0.113.7", "100.64.0.1"]
    results: list[LookupResult] = []
    for text in demo_ips:
        address = parse_address(text)
        category, detail = classify(address)
        result = LookupResult(ip=str(address), category=category, detail=detail)
        results.append(result)
        print("  " + describe(result))

    print("\nDemo: public address lookup (network optional, 2s timeout)\n")
    public = lookup_public("8.8.8.8", timeout=2.0)
    results.append(public)
    print("  " + describe(public))
    if public.error:
        print("  Graceful fallback: no country data available offline.")
    else:
        print(f"  Source: ipwho.is; country={public.country} ({public.country_code})")

    print(f"\nDemo complete: {len(results)} addresses handled, exit 0 regardless of network.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2

    try:
        targets = gather_targets(args.ips, args.file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.me:
        if targets:
            print("error: --me cannot be combined with explicit addresses", file=sys.stderr)
            return 2
        result = lookup_public(None, args.timeout)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print(describe(result))
        return 0 if not result.error else 1

    if not targets and sys.stdin.isatty():
        try:
            entered = input("IP address(es), space separated: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        targets = entered.split()

    if not targets:
        print("error: provide one or more IP addresses, --file or --me", file=sys.stderr)
        return 2

    results: list[LookupResult] = []
    failures = 0
    for text in targets:
        try:
            address = parse_address(text)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue
        category, detail = classify(address)
        if category == "public":
            result = lookup_public(str(address), args.timeout)
            failures += 1 if result.error else 0
        else:
            result = LookupResult(ip=str(address), category=category, detail=detail)
        results.append(result)
        if not args.json:
            print(describe(result))

    if args.json:
        print(json.dumps([asdict(item) for item in results], indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
