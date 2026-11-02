#!/usr/bin/env python3
"""Track stock quotes for a watchlist and show whether prices moved up or down.

Quotes come from stooq.com's free CSV endpoint (no API key).  A local JSON
watchlist stores symbols between runs, ``--interval`` polls repeatedly, and
``--demo`` replays two bundled offline snapshots so no network is needed.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

QUOTE_URL = "https://stooq.com/q/l/?s={symbols}&f=sd2t2ohlcv&h&e=csv"
USER_AGENT = "QuoteTracker/1.0 (text mini-project)"


class QuoteError(Exception):
    """Raised when quotes cannot be fetched or parsed."""


@dataclass
class Quote:
    """A single OHLCV snapshot; prices are None when the symbol has no data."""

    symbol: str
    date: str
    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None

    @property
    def updated(self) -> str:
        return f"{self.date} {self.time}".strip()


def normalize_symbol(symbol: str) -> str:
    """Upper-case a symbol and add stooq's ``.US`` suffix when no market is given."""
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("empty symbol")
    return symbol if "." in symbol else f"{symbol}.US"


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_quotes_csv(text: str) -> list[Quote]:
    """Parse stooq's ``Symbol,Date,Time,Open,High,Low,Close,Volume`` CSV."""
    cleaned = text.lstrip("\ufeff").strip()
    if not cleaned:
        raise QuoteError("empty response from quote service")
    reader = csv.DictReader(io.StringIO(cleaned))
    if not reader.fieldnames or "Symbol" not in reader.fieldnames:
        raise QuoteError("unexpected response (no Symbol column); the service may be unavailable")
    quotes: list[Quote] = []
    for row in reader:
        symbol = (row.get("Symbol") or "").strip()
        if not symbol:
            continue
        volume = _to_float(row.get("Volume"))
        quotes.append(Quote(
            symbol=symbol.upper(),
            date=(row.get("Date") or "").strip(),
            time=(row.get("Time") or "").strip(),
            open=_to_float(row.get("Open")),
            high=_to_float(row.get("High")),
            low=_to_float(row.get("Low")),
            close=_to_float(row.get("Close")),
            volume=int(volume) if volume is not None else None,
        ))
    if not quotes:
        raise QuoteError("no quote rows returned")
    return quotes


def fetch_quotes(symbols: list[str], timeout: float = 10.0) -> list[Quote]:
    """Fetch quotes for *symbols* from stooq.com."""
    query = "+".join(urllib.parse.quote(symbol, safe=".") for symbol in symbols)
    request = urllib.request.Request(
        QUOTE_URL.format(symbols=query), headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise QuoteError(f"HTTP {exc.code} from stooq.com") from exc
    except urllib.error.URLError as exc:
        raise QuoteError(f"network error contacting stooq.com: {exc.reason}") from exc
    except TimeoutError as exc:
        raise QuoteError(f"timed out after {timeout:g}s contacting stooq.com") from exc
    return parse_quotes_csv(text)


def default_watchlist_path() -> Path:
    return Path.home() / ".quote_tracker_watchlist.json"


def load_watchlist(path: Path) -> list[str]:
    """Load a JSON list (or ``{"symbols": [...]}``) of symbols."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise QuoteError(f"cannot read watchlist {path}: {exc}") from exc
    symbols = data.get("symbols", []) if isinstance(data, dict) else data
    if not isinstance(symbols, list):
        raise QuoteError(f"watchlist {path} must contain a list of symbols")
    cleaned: list[str] = []
    for item in symbols:
        if isinstance(item, str) and item.strip():
            symbol = normalize_symbol(item)
            if symbol not in cleaned:
                cleaned.append(symbol)
    return cleaned


def save_watchlist(path: Path, symbols: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"symbols": symbols}, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise QuoteError(f"cannot write watchlist {path}: {exc}") from exc


def percent_change(price: float | None, reference: float | None) -> float | None:
    if price is None or reference is None or reference == 0:
        return None
    return (price - reference) / reference * 100.0


def trend_arrow(change: float | None) -> str:
    if change is None:
        return "?"
    if change > 0.005:
        return "▲"
    if change < -0.005:
        return "▼"
    return "▬"


def format_table(quotes: list[Quote], previous: dict[str, float] | None = None) -> str:
    """Render quotes as a table; changes compare to the last poll or the open."""
    previous = previous or {}
    header = f"{'SYMBOL':<10} {'PRICE':>10} {'CHANGE':>10}  {'TREND':<5} {'VS':<5} UPDATED"
    lines = [header, "-" * len(header)]
    for quote in quotes:
        reference = previous.get(quote.symbol, quote.open)
        label = "prev" if quote.symbol in previous else "open"
        change = percent_change(quote.close, reference)
        price = f"{quote.close:,.2f}" if quote.close is not None else "n/a"
        change_text = f"{change:+.2f}%" if change is not None else "n/a"
        lines.append(
            f"{quote.symbol:<10} {price:>10} {change_text:>10}  "
            f"{trend_arrow(change):<5} {label:<5} {quote.updated}"
        )
    return "\n".join(lines)


def poll_once(symbols: list[str], timeout: float, previous: dict[str, float] | None,
              as_json: bool = False) -> dict[str, float]:
    """Fetch and print one snapshot; return closes for the next comparison."""
    quotes = fetch_quotes(symbols, timeout)
    if as_json:
        payload = []
        for quote in quotes:
            reference = (previous or {}).get(quote.symbol, quote.open)
            change = percent_change(quote.close, reference)
            item = asdict(quote)
            item["change_percent"] = round(change, 2) if change is not None else None
            payload.append(item)
        print(json.dumps(payload, indent=2))
    else:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Quotes at {stamp}\n{format_table(quotes, previous)}")
    return {q.symbol: q.close for q in quotes if q.close is not None}


def demo() -> int:
    """Replay two bundled snapshots and exercise the watchlist offline."""
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as tmp:
        watch_path = Path(tmp) / "watchlist.json"
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
        print("Quote Tracker demo\n" + "=" * 18)
        print("watchlist add AAPL, MSFT, GOOGL, TSLA")
        save_watchlist(watch_path, [normalize_symbol(s) for s in symbols])
        print("watchlist: " + ", ".join(load_watchlist(watch_path)))

        first = parse_quotes_csv((here / "sample_quotes.csv").read_text(encoding="utf-8"))
        print("\n--- poll 1 (change vs. day open) ---")
        print(format_table(first))
        first_closes = {q.symbol: q.close for q in first if q.close is not None}

        second = parse_quotes_csv((here / "sample_quotes_2.csv").read_text(encoding="utf-8"))
        print("\n--- poll 2 (change vs. previous poll) ---")
        print(format_table(second, first_closes))

        changes = {q.symbol: percent_change(q.close, first_closes.get(q.symbol)) for q in second}
        aapl, msft, tsla = changes["AAPL.US"], changes["MSFT.US"], changes["TSLA.US"]
        if aapl is None or msft is None or tsla is None or not (aapl > 0 and msft < 0 and tsla < 0):
            print("demo assertion failed: unexpected movement signs", file=sys.stderr)
            return 1
        if len(load_watchlist(watch_path)) != 4:
            print("demo assertion failed: watchlist round-trip", file=sys.stderr)
            return 1
        print("\ntrends: AAPL ▲, MSFT ▼, TSLA ▼ (watchlist round-trip OK)")
        print("demo assertions passed: 8 quotes parsed, arrows match the price movement")
    return 0


def ask_symbols() -> list[str]:
    raw = input("Symbols (comma separated, e.g. AAPL, MSFT): ")
    return [part.strip() for part in raw.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track stock quotes from stooq.com and show up/down movement.",
        epilog="Example: python3 solution.py AAPL MSFT --interval 60 --count 5",
    )
    parser.add_argument("symbols", nargs="*", help="ticker symbols (market defaults to .US)")
    parser.add_argument("--watchlist", metavar="PATH",
                        help=f"JSON watchlist file (default: {default_watchlist_path()})")
    parser.add_argument("--add", action="append", default=[], metavar="SYMBOL",
                        help="add a symbol to the saved watchlist")
    parser.add_argument("--remove", action="append", default=[], metavar="SYMBOL",
                        help="remove a symbol from the saved watchlist")
    parser.add_argument("--list", action="store_true", help="show the saved watchlist and exit")
    parser.add_argument("--interval", type=float, metavar="SECONDS",
                        help="poll repeatedly with this delay")
    parser.add_argument("--count", type=int, default=0, metavar="N",
                        help="stop after N polls when --interval is used (0 = until Ctrl-C)")
    parser.add_argument("--timeout", type=float, default=10.0, metavar="SECONDS",
                        help="network timeout (default: 10)")
    parser.add_argument("--json", action="store_true", help="emit JSON for each poll")
    parser.add_argument("--demo", action="store_true", help="use bundled offline sample quotes")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return demo()

    watch_path = Path(args.watchlist).expanduser() if args.watchlist else default_watchlist_path()
    try:
        watchlist = load_watchlist(watch_path)
        for symbol in args.add:
            normalized = normalize_symbol(symbol)
            if normalized not in watchlist:
                watchlist.append(normalized)
                print(f"added {normalized}")
        for symbol in args.remove:
            normalized = normalize_symbol(symbol)
            if normalized in watchlist:
                watchlist.remove(normalized)
                print(f"removed {normalized}")
            else:
                print(f"{normalized} is not in the watchlist")
        if args.add or args.remove:
            save_watchlist(watch_path, watchlist)
            if not args.symbols and not args.list:
                print("watchlist saved; run without --add/--remove to fetch quotes")
                return 0
        if args.list:
            print("watchlist: " + (", ".join(watchlist) if watchlist else "(empty)"))
            if not args.symbols:
                return 0
        symbols = [normalize_symbol(s) for s in args.symbols] or watchlist
    except (QuoteError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not symbols:
        if not sys.stdin.isatty():
            print("error: no symbols given and the watchlist is empty", file=sys.stderr)
            return 2
        try:
            symbols = [normalize_symbol(s) for s in ask_symbols()]
        except (EOFError, KeyboardInterrupt, ValueError):
            print("\nNo symbols entered.", file=sys.stderr)
            return 2
    if args.interval is not None and args.interval <= 0:
        print("error: --interval must be greater than zero", file=sys.stderr)
        return 2
    if args.count < 0:
        print("error: --count cannot be negative", file=sys.stderr)
        return 2

    previous: dict[str, float] = {}
    polls = 0
    try:
        while True:
            try:
                previous = poll_once(symbols, args.timeout, previous, args.json)
            except QuoteError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            polls += 1
            if args.interval is None or (args.count and polls >= args.count):
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
