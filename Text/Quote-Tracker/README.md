# Quote Tracker (market symbols etc)

*Category: Text · Project directory: `Text/Quote-Tracker/`*

## Problem

A program which can go out and check the current value of stocks for a list of symbols entered by the user. The user can set how often the stocks are checked. For CLI, show whether the stock has moved up or down.

## Features

- Fetches current OHLCV quotes from stooq.com's free CSV endpoint (no API key).
- Accepts symbols on the command line and normalizes them (`AAPL` → `AAPL.US`).
- Persistent JSON watchlist with `--add`, `--remove`, and `--list`.
- Shows price, percentage change, an up/down arrow, and the comparison basis.
- First poll compares the close to the day's open; later polls compare to the previous poll.
- `--interval` repeats polling; `--count` bounds the number of polls.
- `--json` for machine-readable snapshots, `--timeout` for slow connections.
- `--demo` replays two bundled CSV snapshots offline.

## Requirements

Python 3.10+ (standard library only: `urllib`, `csv`, `json`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py AAPL MSFT
python3 solution.py --add TSLA
python3 solution.py --list
python3 solution.py --interval 60 --count 5
python3 solution.py AAPL MSFT --interval 30
```

| Option | Meaning |
| --- | --- |
| `symbols` | One or more tickers; a market suffix is added when omitted. |
| `--watchlist PATH` | JSON file (default `~/.quote_tracker_watchlist.json`). |
| `--add SYMBOL` / `--remove SYMBOL` | Edit the saved watchlist (repeatable). |
| `--list` | Print the watchlist. |
| `--interval SECONDS` | Poll repeatedly with this delay. |
| `--count N` | Stop after N polls (0 = until Ctrl-C). |
| `--timeout SECONDS` | Per-request timeout (default 10). |
| `--json` | Print each snapshot as JSON. |
| `--demo` | Use the bundled sample CSVs; no network. |

With no symbols, the saved watchlist is used; on a terminal with an empty watchlist the program prompts for symbols.

## Example Output

```text
Quote Tracker demo
==================
watchlist add AAPL, MSFT, GOOGL, TSLA
watchlist: AAPL.US, MSFT.US, GOOGL.US, TSLA.US

--- poll 1 (change vs. day open) ---
SYMBOL          PRICE     CHANGE  TREND VS    UPDATED
-----------------------------------------------------
AAPL.US        194.03     +0.93%  ▲     open  2024-06-03 22:00:05
MSFT.US        416.75     +0.30%  ▲     open  2024-06-03 22:00:05
GOOGL.US       175.90     +1.03%  ▲     open  2024-06-03 22:00:05
TSLA.US        176.20     -0.11%  ▼     open  2024-06-03 22:00:05

--- poll 2 (change vs. previous poll) ---
SYMBOL          PRICE     CHANGE  TREND VS    UPDATED
-----------------------------------------------------
AAPL.US        195.02     +0.51%  ▲     prev  2024-06-03 22:05:05
MSFT.US        415.90     -0.20%  ▼     prev  2024-06-03 22:05:05
GOOGL.US       176.55     +0.37%  ▲     prev  2024-06-03 22:05:05
TSLA.US        173.10     -1.76%  ▼     prev  2024-06-03 22:05:05
```

## Implementation Notes

- One request is made for all symbols: `https://stooq.com/q/l/?s=aapl.us+msft.us&f=sd2t2ohlcv&h&e=csv`. The CSV is parsed into `Quote` dataclasses; `N/A` prices become `None` and display as `n/a`.
- Percent change is `(close - reference) / reference * 100`. The reference is the previous poll's close when available, otherwise the day's open, so a single snapshot still communicates direction.
- Arrows use Unicode (`▲`, `▼`, `▬`); a change smaller than 0.005% counts as flat.
- The watchlist is a small JSON file (`{"symbols": [...]}`) written under the user's home directory by default; pass `--watchlist` to keep it elsewhere.
- stooq's free endpoint can rate-limit, block automated clients (HTTP 404), or be unavailable; failures print a single message and exit 1. The demo is fully offline and deterministic.

This is a demonstration tool, not investment advice.
