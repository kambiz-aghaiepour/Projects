#!/usr/bin/env python3
"""Page Scraper - crawl a web page and index its links and images.

The crawler fetches a seed page (optionally following same-site links up to a
depth and page limit), extracts ``<a href>`` and ``<img src>`` targets, resolves
them to absolute URLs, removes fragments and duplicates, and writes a JSON or
CSV index.  ``--demo`` serves a tiny site from a local HTTP server so the whole
pipeline can be exercised without internet access.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
import threading
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "page-scraper/1.0 (+stdlib; educational)"
LOCALHOST = "127.0.0.1"
SKIP_SCHEMES = {"mailto", "tel", "javascript", "data", "ftp", "file"}


@dataclass
class Asset:
    """One unique link or image discovered during a crawl."""

    kind: str
    url: str
    text: str = ""
    sources: list[str] = field(default_factory=list)


@dataclass
class Page:
    """A successfully fetched page."""

    url: str
    title: str
    depth: int


@dataclass
class CrawlResult:
    """Everything the crawler collected, ready to serialise."""

    seed: str
    pages: list[Page]
    assets: list[Asset]
    errors: list[tuple[str, str]]

    @property
    def links(self) -> list[Asset]:
        """Return indexed anchors."""
        return [asset for asset in self.assets if asset.kind == "link"]

    @property
    def images(self) -> list[Asset]:
        """Return indexed images."""
        return [asset for asset in self.assets if asset.kind == "image"]


class _Extractor(HTMLParser):
    """Collect anchors, images, the base URL and the document title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base_href: str | None = None
        self.anchors: list[tuple[str, str]] = []
        self.images: list[tuple[str, str]] = []
        self.title = ""
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        if tag == "base" and values.get("href"):
            self.base_href = values["href"]
        elif tag == "a" and values.get("href"):
            self._anchor_href = values["href"]
            self._anchor_text = []
        elif tag == "img" and values.get("src"):
            self.images.append((values["src"], values.get("alt", "")))
        elif tag == "title":
            self._in_title = True
            self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            text = " ".join("".join(self._anchor_text).split())
            self.anchors.append((self._anchor_href, text))
            self._anchor_href = None
            self._anchor_text = []
        elif tag == "title" and self._in_title:
            self.title = " ".join("".join(self._title_parts).split())
            self._in_title = False


def clean_url(raw: str, base: str) -> str | None:
    """Resolve ``raw`` against ``base`` and return a deduplicated HTTP(S) URL."""
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    absolute = urljoin(base, raw)
    absolute, _fragment = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme.lower() not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    return absolute


def fetch_page(url: str, timeout: float) -> tuple[str, str]:
    """Fetch ``url`` and return ``(html, final_url)``."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(2_000_000)  # cap runaway pages at ~2 MB
        return body.decode(charset, errors="replace"), response.geturl()


class Crawler:
    """Breadth-first crawler with depth, page and domain limits."""

    def __init__(self, max_pages: int = 10, max_depth: int = 1,
                 same_domain: bool = True, timeout: float = 10.0) -> None:
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.same_domain = same_domain
        self.timeout = timeout
        self._assets: dict[tuple[str, str], Asset] = {}

    def _record(self, kind: str, raw: str, base: str, text: str, source: str) -> str | None:
        url = clean_url(raw, base)
        if url is None:
            return None
        key = (kind, url)
        asset = self._assets.get(key)
        if asset is None:
            self._assets[key] = Asset(kind, url, text, [source])
        else:
            if not asset.text and text:
                asset.text = text
            if source not in asset.sources:
                asset.sources.append(source)
        return url

    def _allowed(self, url: str, seed_host: str) -> bool:
        return not self.same_domain or urlparse(url).netloc.lower() == seed_host

    def crawl(self, seed: str) -> CrawlResult:
        """Crawl from ``seed`` and return the collected index."""
        seed_host = urlparse(seed).netloc.lower()
        queue: deque[tuple[str, int]] = deque([(seed, 0)])
        visited: set[str] = set()
        pages: list[Page] = []
        errors: list[tuple[str, str]] = []

        while queue and len(pages) < self.max_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                html, final_url = fetch_page(url, self.timeout)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append((url, f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"))
                continue

            parser = _Extractor()
            try:
                parser.feed(html)
                parser.close()
            except Exception as exc:  # html.parser is lenient, but stay safe
                errors.append((url, f"parse error: {exc}"))
                continue

            base = urljoin(final_url, parser.base_href) if parser.base_href else final_url
            pages.append(Page(final_url, parser.title or "(untitled)", depth))

            followable: list[str] = []
            for href, text in parser.anchors:
                resolved = self._record("link", href, base, text, final_url)
                if resolved and depth < self.max_depth and resolved not in visited:
                    followable.append(resolved)
            for src, alt in parser.images:
                self._record("image", src, base, alt, final_url)

            for link in followable:
                if self._allowed(link, seed_host):
                    queue.append((link, depth + 1))

        return CrawlResult(seed, pages, sorted(self._assets.values(),
                                               key=lambda a: (a.kind, a.url)), errors)


def build_payload(result: CrawlResult) -> dict:
    """Build the JSON-serialisable index document."""
    return {
        "seed": result.seed,
        "counts": {
            "pages": len(result.pages),
            "links": len(result.links),
            "images": len(result.images),
            "total": len(result.assets),
        },
        "pages": [{"url": p.url, "title": p.title, "depth": p.depth} for p in result.pages],
        "items": [
            {"kind": a.kind, "url": a.url, "text": a.text, "sources": a.sources}
            for a in result.assets
        ],
        "errors": [{"url": url, "error": error} for url, error in result.errors],
    }


def render_csv(result: CrawlResult) -> str:
    """Build a CSV index with one row per unique asset."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["kind", "url", "text", "sources"])
    for asset in result.assets:
        writer.writerow([asset.kind, asset.url, asset.text, ";".join(asset.sources)])
    return buffer.getvalue()


def write_index(result: CrawlResult, destination: str, fmt: str) -> int:
    """Write the index to ``destination`` (``-`` for stdout) and return its size."""
    if fmt == "json":
        content = json.dumps(build_payload(result), indent=2, ensure_ascii=False) + "\n"
    else:
        content = render_csv(result)
    if destination == "-":
        print(content, end="")
        return len(content.encode("utf-8"))
    path = Path(destination)
    path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def print_summary(result: CrawlResult, verbose: bool = False,
                  stream: TextIO = sys.stdout) -> None:
    """Print page/item counts and a short table of indexed assets."""
    payload = build_payload(result)
    counts = payload["counts"]
    print(f"Fetched {counts['pages']} page(s), indexed {counts['total']} unique item(s) "
          f"({counts['links']} links, {counts['images']} images).", file=stream)
    shown = result.assets if verbose else result.assets[:20]
    if shown:
        print(file=stream)
        print(f"{'KIND':<6} {'URL':<58} TEXT", file=stream)
        print("-" * 96, file=stream)
        for asset in shown:
            text = asset.text if len(asset.text) <= 24 else asset.text[:21] + "..."
            url = asset.url if len(asset.url) <= 58 else asset.url[:55] + "..."
            print(f"{asset.kind:<6} {url:<58} {text}", file=stream)
        if len(shown) < len(result.assets):
            print(f"... {len(result.assets) - len(shown)} more item(s); use --verbose to list all",
                  file=stream)
    for url, error in result.errors:
        print(f"warning: {url}: {error}", file=sys.stderr)


def format_for(path: str) -> str:
    """Infer the index format from a file extension."""
    return "csv" if path.lower().endswith(".csv") else "json"


def run_crawl(seed: str, args: argparse.Namespace) -> int:
    """Crawl, print a summary and write the requested index."""
    normalized = seed if "://" in seed else "http://" + seed
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(f"error: not a valid http(s) URL: {seed!r}", file=sys.stderr)
        return 2
    stream = sys.stderr if args.output == "-" else sys.stdout
    print(f"Crawling {normalized} (max_pages={args.max_pages}, depth={args.depth}, "
          f"same_domain={'yes' if not args.cross_domain else 'no'})", file=stream)
    result = Crawler(args.max_pages, args.depth, not args.cross_domain, args.timeout).crawl(normalized)
    if not result.pages:
        print("error: could not fetch any page", file=sys.stderr)
        for url, error in result.errors:
            print(f"  {url}: {error}", file=sys.stderr)
        return 1
    print_summary(result, args.verbose, stream)
    fmt = args.format or format_for(args.output)
    try:
        size = write_index(result, args.output, fmt)
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
        return 1
    target = "stdout" if args.output == "-" else args.output
    print(f"\nIndex written to {target} ({fmt}, {size} bytes).", file=stream)
    return 0


# --------------------------------------------------------------------------- demo

_DEMO_PAGES = {
    "/": """<!doctype html><html><head><title>Demo Home</title></head><body>
        <h1>Scraper demo</h1>
        <a href="/about.html">About us</a>
        <a href="blog/post.html">Blog post</a>
        <a href="/about.html#team">About (team section)</a>
        <a href="mailto:hello@example.com">Mail us</a>
        <a href="https://example.org/external">External site</a>
        <img src="/static/logo.png" alt="Demo logo">
        <img src="static/logo.png" alt="Demo logo duplicate">
    </body></html>""",
    "/about.html": """<!doctype html><html><head><title>About</title></head><body>
        <a href="/">Home</a>
        <a href="/contact.html">Contact</a>
        <img src="img/team.png" alt="The team">
    </body></html>""",
    "/blog/post.html": """<!doctype html><html><head><title>Blog post</title></head><body>
        <a href="../about.html">Back to about</a>
        <a href="/blog/post.html?ref=footer">Permalink</a>
        <img src="../img/chart.png" alt="Chart">
    </body></html>""",
    "/contact.html": """<!doctype html><html><head><title>Contact</title></head><body>
        <a href="/">Home</a><a href="/about.html">About</a>
    </body></html>""",
}


def _demo_handler(pages: dict[str, str]) -> type[BaseHTTPRequestHandler]:
    """Create a request handler that serves an in-memory site."""

    class DemoHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            path = urlparse(self.path).path
            body = pages.get(path)
            if body is None:
                self.send_error(404, "not found")
                return
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            """Silence request logs so demo output stays readable."""

    return DemoHandler


def run_demo() -> int:
    """Serve a small site locally, crawl it and show the generated index."""
    server = ThreadingHTTPServer((LOCALHOST, 0), _demo_handler(_DEMO_PAGES))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    seed = f"http://{LOCALHOST}:{port}/"
    print("Page Scraper demo (offline: the site below is served from this process)")
    print(f"Demo site: {seed}\n")
    try:
        result = Crawler(max_pages=10, max_depth=1, same_domain=True, timeout=5.0).crawl(seed)
        print_summary(result, verbose=True)
        expected = {"links": 6, "images": 3, "pages": 3}
        actual = {"links": len(result.links), "images": len(result.images),
                  "pages": len(result.pages)}
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "index.json"
            csv_path = Path(tmp) / "index.csv"
            json_size = write_index(result, str(json_path), "json")
            write_index(result, str(csv_path), "csv")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            print(f"\nJSON index: {json_size} bytes, {len(payload['items'])} items, "
                  f"{len(payload['pages'])} pages.")
            print(f"CSV index: {csv_path.stat().st_size} bytes, "
                  f"{len(csv_path.read_text(encoding='utf-8').splitlines()) - 1} data rows.")
            print("First JSON item:", json.dumps(payload["items"][0], ensure_ascii=False))
        # Every page-level link is unique after de-duplication; duplicate
        # logo.png appears once, and the external link is indexed but not fetched.
        unique_urls = {asset.url for asset in result.assets}
        print(f"\nUnique URLs: {len(unique_urls)}; pages fetched: {len(result.pages)}; "
              f"external host fetched: {any('example.org' in p.url for p in result.pages)}")
        if actual != expected or len(unique_urls) != len(result.assets):
            print(f"demo: unexpected counts {actual}", file=sys.stderr)
            return 1
        if any("example.org" in p.url for p in result.pages):
            print("demo: same-domain restriction failed", file=sys.stderr)
            return 1
    finally:
        server.shutdown()
        server.server_close()
    print("\nDemo complete: 3 pages crawled, duplicates removed, JSON and CSV written.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Crawl a page and index its links and images (no duplicates).",
        epilog="Examples:\n"
               "  python3 solution.py https://example.com --depth 1 --output index.json\n"
               "  python3 solution.py example.com --depth 0 --format csv --output links.csv\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="seed URL (scheme optional)")
    parser.add_argument("--max-pages", type=int, default=10,
                        help="maximum pages to fetch (default: 10)")
    parser.add_argument("--depth", type=int, default=1,
                        help="link hops to follow; 0 = seed page only (default: 1)")
    parser.add_argument("--cross-domain", action="store_true",
                        help="follow links to other hosts (default: stay on the seed host)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="per-request timeout in seconds (default: 10)")
    parser.add_argument("--output", default="index.json",
                        help="index file, or '-' for stdout (default: index.json)")
    parser.add_argument("--format", choices=("json", "csv"),
                        help="index format; inferred from --output otherwise")
    parser.add_argument("--verbose", action="store_true", help="list every indexed item")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.depth < 0:
        parser.error("--depth cannot be negative")
    if not args.url:
        if not sys.stdin.isatty():
            parser.error("a URL is required (or use --demo)")
        try:
            args.url = input("Seed URL: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.url:
            print("error: no URL entered", file=sys.stderr)
            return 2
    return run_crawl(args.url, args)


if __name__ == "__main__":
    raise SystemExit(main())
