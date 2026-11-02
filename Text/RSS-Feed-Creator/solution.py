#!/usr/bin/env python3
"""Read an RSS 2.0, RSS 1.0 (RDF), or Atom feed and print its entries.

Feeds can be loaded from a URL or a local file.  The parser uses only
``xml.etree.ElementTree`` and understands the common title/link/date fields of
both formats.  ``--demo`` parses two bundled sample feeds offline.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

USER_AGENT = "RSSFeedCreator/1.0 (text mini-project)"
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


class FeedError(Exception):
    """Raised when a source cannot be fetched or parsed as a feed."""


@dataclass
class Entry:
    """One feed item or Atom entry."""

    title: str
    link: str
    published: str
    summary: str


def local_name(tag: str) -> str:
    """Return an element tag without its XML namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, *names: str) -> str:
    """Return stripped text of the first direct child whose local tag matches."""
    wanted = {name.lower() for name in names}
    for child in element:
        if local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def clean_summary(raw: str, limit: int = 240) -> str:
    """Strip markup and collapse whitespace in a description/summary."""
    text = SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", raw))).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_date(raw: str) -> str:
    """Convert RFC 822 or ISO 8601 dates to ISO 8601 UTC; keep unknown text."""
    raw = raw.strip()
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return raw


def atom_link(element: ET.Element) -> str:
    """Pick the alternate (or first) Atom link href."""
    fallback = ""
    for child in element:
        if local_name(child.tag) != "link":
            continue
        href = child.get("href", "").strip()
        if not href:
            continue
        if child.get("rel", "alternate") == "alternate":
            return href
        fallback = fallback or href
    return fallback


def parse_feed(data: bytes) -> tuple[str, str, list[Entry]]:
    """Parse feed bytes into ``(feed_title, format_name, entries)``."""
    if not data.strip():
        raise FeedError("the feed is empty")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FeedError(f"invalid XML: {exc}") from exc

    kind = local_name(root.tag)
    if kind == "rss":
        channel = next((c for c in root if local_name(c.tag) == "channel"), None)
        if channel is None:
            raise FeedError("RSS document has no <channel>")
        title = child_text(channel, "title") or "(untitled feed)"
        entries = [rss_entry(item) for item in channel if local_name(item.tag) == "item"]
        return title, "rss", entries
    if kind == "rdf":
        title = ""
        entries = []
        for child in root:
            name = local_name(child.tag)
            if name == "channel":
                title = child_text(child, "title")
            elif name == "item":
                entries.append(rss_entry(child))
        return title or "(untitled feed)", "rss1", entries
    if kind == "feed":
        title = child_text(root, "title") or "(untitled feed)"
        entries = [atom_entry(e) for e in root if local_name(e.tag) == "entry"]
        return title, "atom", entries
    raise FeedError(f"unsupported root element <{local_name(root.tag)}> (expected rss, RDF, or feed)")


def rss_entry(item: ET.Element) -> Entry:
    description = child_text(item, "description", "encoded", "summary")
    return Entry(
        title=child_text(item, "title") or "(untitled)",
        link=child_text(item, "link"),
        published=normalize_date(child_text(item, "pubdate", "date", "published", "updated")),
        summary=clean_summary(description),
    )


def atom_entry(entry: ET.Element) -> Entry:
    summary = child_text(entry, "summary", "content")
    return Entry(
        title=child_text(entry, "title") or "(untitled)",
        link=atom_link(entry),
        published=normalize_date(child_text(entry, "published", "updated")),
        summary=clean_summary(summary),
    )


def fetch(url: str, timeout: float) -> bytes:
    """Download a feed over HTTP(S) with a descriptive error on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise FeedError(f"HTTP {exc.code} while fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise FeedError(f"network error while fetching {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FeedError(f"timed out after {timeout:g}s fetching {url}") from exc


def load_source(source: str, timeout: float) -> bytes:
    """Read feed bytes from a URL, a local file, or stdin (``-``)."""
    if source == "-":
        return sys.stdin.buffer.read()
    if source.startswith(("http://", "https://")):
        return fetch(source, timeout)
    path = Path(source).expanduser()
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FeedError(f"cannot read {source}: {exc.strerror or exc}") from exc


def render(title: str, source: str, kind: str, entries: list[Entry], total: int) -> str:
    """Format a feed as human-readable text."""
    lines = [f"Feed: {title}", f"Source: {source} ({kind})"]
    shown = f"{len(entries)} of {total}" if len(entries) != total else str(total)
    lines.append(f"Entries: {shown}")
    for number, entry in enumerate(entries, 1):
        lines.append("")
        lines.append(f"{number:>2}. {entry.title}")
        if entry.published:
            lines.append(f"    {entry.published}")
        if entry.link:
            lines.append(f"    {entry.link}")
        if entry.summary:
            lines.append(f"    {entry.summary}")
    return "\n".join(lines)


def demo() -> int:
    """Parse the bundled RSS and Atom samples without touching the network."""
    here = Path(__file__).resolve().parent
    cases = [
        ("sample_feed.xml", "rss"),
        ("sample_atom.xml", "atom"),
    ]
    print("RSS Feed Creator demo\n" + "=" * 22)
    results: dict[str, tuple[str, str, list[Entry]]] = {}
    for filename, expected_kind in cases:
        data = (here / filename).read_bytes()
        title, kind, entries = parse_feed(data)
        results[kind] = (title, kind, entries)
        print()
        print(render(title, filename, kind, entries[:3], len(entries)))
        if kind != expected_kind or not entries:
            print(f"demo assertion failed for {filename}", file=sys.stderr)
            return 1

    print("\n--- --limit 2 as JSON ---")
    title, kind, entries = results["rss"]
    payload = {
        "feed": title,
        "format": kind,
        "count": min(2, len(entries)),
        "entries": [asdict(entry) for entry in entries[:2]],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    print("\n--- error handling ---")
    try:
        parse_feed(b"<rss><channel><title>broken")
    except FeedError as exc:
        print(f"caught invalid feed as expected: {exc}")
    else:
        print("demo assertion failed: malformed XML was accepted", file=sys.stderr)
        return 1

    rss_entries = results["rss"][2]
    atom_entries = results["atom"][2]
    if len(rss_entries) != 4 or len(atom_entries) != 3:
        print("demo assertion failed: unexpected entry counts", file=sys.stderr)
        return 1
    if not rss_entries[0].published.startswith("2024-05-01T09:30:00"):
        print("demo assertion failed: RSS date was not normalized", file=sys.stderr)
        return 1
    if not atom_entries[0].link.startswith("https://example.org/"):
        print("demo assertion failed: Atom link was not read", file=sys.stderr)
        return 1
    print("demo assertions passed: 4 RSS items, 3 Atom entries, dates normalized")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read an RSS 2.0, RSS 1.0, or Atom feed and list its entries.",
        epilog="Example: python3 solution.py https://example.com/feed.xml --limit 5",
    )
    parser.add_argument("source", nargs="?", help="feed URL or local XML file ('-' for stdin)")
    parser.add_argument("--limit", type=int, default=10, metavar="N",
                        help="show at most N entries; 0 shows all (default: 10)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS",
                        help="network timeout (default: 10)")
    parser.add_argument("--demo", action="store_true", help="parse the bundled sample feeds")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return demo()
    if not args.source:
        parser.print_usage(sys.stderr)
        print("error: a feed URL or file is required (or use --demo)", file=sys.stderr)
        return 2
    if args.limit < 0:
        print("error: --limit must be 0 or greater", file=sys.stderr)
        return 2
    try:
        data = load_source(args.source, args.timeout)
        title, kind, entries = parse_feed(data)
    except FeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    selected = entries if args.limit == 0 else entries[: args.limit]
    if args.json:
        print(json.dumps({
            "feed": title,
            "source": args.source,
            "format": kind,
            "count": len(selected),
            "entries": [asdict(entry) for entry in selected],
        }, indent=2, ensure_ascii=False))
    else:
        print(render(title, args.source, kind, selected, len(entries)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
