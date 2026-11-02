# RSS Feed Creator

*Category: Text · Project directory: `Text/RSS-Feed-Creator/`*

## Problem

Given a link to RSS/Atom Feed, get all posts and display them.

## Features

- Reads RSS 2.0, RSS 1.0 (RDF), and Atom feeds.
- Loads from an HTTP(S) URL, a local file, or stdin (`-`).
- Displays title, publication date, link, and a short summary for every entry.
- `--limit N` caps the listing; `--limit 0` shows everything.
- `--json` emits structured output for scripting.
- Normalizes RFC 822 and ISO 8601 dates to ISO 8601 UTC.
- Two bundled sample feeds for a fully offline `--demo`.
- Graceful messages for network failures, malformed XML, and unsupported feed roots.

## Requirements

Python 3.10+ (standard library only: `urllib`, `xml.etree.ElementTree`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py https://example.com/feed.xml --limit 5
python3 solution.py sample_feed.xml --json
python3 solution.py sample_atom.xml --limit 0
curl -s https://example.com/feed.xml | python3 solution.py - --limit 3
```

| Option | Meaning |
| --- | --- |
| `source` | Feed URL, local XML path, or `-` for stdin. |
| `--limit N` | Show at most N entries (default 10; 0 = all). |
| `--json` | Output one JSON object with feed metadata and entries. |
| `--timeout SECONDS` | Network timeout (default 10). |
| `--demo` | Parse the bundled RSS and Atom samples offline. |

## Example Output

```text
RSS Feed Creator demo
======================

Feed: Example Tech Notes
Source: sample_feed.xml (rss)
Entries: 3 of 4

 1. Python 3.13 ships an experimental free-threaded build
    2024-05-01T09:30:00+00:00
    https://example.com/posts/python-313
    The release adds a no-GIL build, a new interactive REPL, and better error messages.

 2. SQLite turns 24 and keeps getting faster
    2024-04-29T16:05:00+00:00
    https://example.com/posts/sqlite-birthday
    A look at the small database that quietly runs half the world.

 3. Why XML still matters for feeds
    2024-04-26T07:45:00+00:00
    https://example.com/posts/xml-feeds
    RSS and Atom remain the simplest way to publish a list of updates.
```

The demo also prints an Atom feed, a JSON excerpt, and a deliberately malformed document to show the error path.

## Implementation Notes

- `xml.etree.ElementTree` parses the document; element names are compared by local name, so RSS and Atom namespaces need no special configuration.
- RSS items use `pubDate`/`dc:date`; Atom entries use `published` or `updated`. Recognized dates are converted to UTC; unknown date strings are passed through unchanged.
- Atom links are selected by `rel="alternate"` (or the first link with an `href`). RSS `link` is read as text.
- Descriptions/summaries are stripped of tags, HTML-unescaped, whitespace-collapsed, and truncated to 240 characters.
- The fetcher sends an identifying User-Agent and does not follow credentials or require API keys. A failed fetch or parse exits non-zero with a one-line message; `--demo` never touches the network.
