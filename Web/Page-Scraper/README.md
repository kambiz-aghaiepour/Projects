# Page Scraper

**Category:** Web · **Project:** Page-Scraper

## Problem

Create an application which connects to a site and pulls out all links, or
images, and saves them to a list. Optional: organize the indexed content,
don't allow duplicates, and put the results into an easily searchable index
file.

## Features

- Crawls a seed URL with a standard-library HTTP client (`urllib`) and parses
  HTML with `html.parser` — no BeautifulSoup required.
- Extracts `<a href>` targets (with their visible text) and `<img src>` targets
  (with their `alt` text).
- Resolves relative URLs, honours `<base href>`, strips fragments, and removes
  duplicate links/images while recording every page where each was found.
- Optional breadth-first crawling (`--depth`) with a page cap (`--max-pages`).
- Stays on the seed host by default; `--cross-domain` allows following external
  links.
- Writes a searchable JSON index or a flat CSV index (format inferred from the
  file extension, or forced with `--format`).
- Per-page fetch errors are collected and reported instead of aborting the run.
- `--demo` serves a four-page site from a local HTTP server, crawls it, verifies
  de-duplication and writes both index formats — fully offline.

## Requirements

Python 3.10+ only; everything uses the standard library.

## Usage

```bash
python3 solution.py --demo
python3 solution.py https://example.com --depth 1 --output index.json
python3 solution.py example.com --depth 0 --format csv --output links.csv
python3 solution.py https://docs.python.org --depth 2 --max-pages 25 --verbose
```

| Option | Meaning |
| --- | --- |
| `url` | Seed page. `http://` is assumed when the scheme is omitted. |
| `--max-pages N` | Stop after N fetched pages (default 10). |
| `--depth N` | Link hops to follow: `0` = seed only, `1` = seed plus its direct links, etc. (default 1). |
| `--cross-domain` | Follow links to other hosts. By default only the seed host is crawled. |
| `--output PATH` | Index destination; `-` writes to stdout (default `index.json`). |
| `--format {json,csv}` | Override the format inferred from the output filename. |
| `--verbose` | List every indexed item rather than the first 20. |
| `--timeout SECONDS` | Per-request timeout (default 10). |
| `--demo` | Run the offline demonstration. |

Running with no URL prompts interactively. Images are indexed by URL; they are
not downloaded.

## Example Output

```
Page Scraper demo (offline: the site below is served from this process)
Demo site: http://127.0.0.1:45105/

Fetched 3 page(s), indexed 9 unique item(s) (6 links, 3 images).

KIND   URL                                                        TEXT
------------------------------------------------------------------------------------------------
image  http://127.0.0.1:45105/img/chart.png                       Chart
image  http://127.0.0.1:45105/img/team.png                        The team
image  http://127.0.0.1:45105/static/logo.png                     Demo logo
link   http://127.0.0.1:45105/                                    Home
link   http://127.0.0.1:45105/about.html                          About us
link   http://127.0.0.1:45105/blog/post.html                      Blog post
link   http://127.0.0.1:45105/blog/post.html?ref=footer           Permalink
link   http://127.0.0.1:45105/contact.html                        Contact
link   https://example.org/external                               External site

JSON index: 2161 bytes, 9 items, 3 pages.
CSV index: 795 bytes, 9 data rows.
First JSON item: {"kind": "image", "url": "http://127.0.0.1:45105/img/chart.png", "text": "Chart", "sources": ["http://127.0.0.1:45105/blog/post.html"]}

Unique URLs: 9; pages fetched: 3; external host fetched: False

Demo complete: 3 pages crawled, duplicates removed, JSON and CSV written.
```

The JSON index has this shape:

```json
{
  "seed": "https://example.com/",
  "counts": {"pages": 3, "links": 6, "images": 3, "total": 9},
  "pages": [{"url": "https://example.com/", "title": "Example", "depth": 0}],
  "items": [{"kind": "link", "url": "https://example.com/about", "text": "About", "sources": ["https://example.com/"]}],
  "errors": []
}
```

## Implementation Notes

`Crawler` runs a breadth-first queue of `(url, depth)` pairs. Each fetched page
is parsed once by `_Extractor`, which records anchors, images, the document
title and any `<base href>`. `clean_url` resolves references with
`urljoin`, removes fragments with `urldefrag`, and rejects non-HTTP(S) schemes
such as `mailto:`. Assets are keyed by `(kind, absolute_url)`, so duplicates
collapse into one entry with a list of source pages.

Only links are followed; the same-host check compares the exact `netloc` (host
and port), so subdomains are treated as external. Page bodies are capped at
2 MB and every request has a timeout. The crawl is O(pages + links) in time and
memory, excluding network latency.

Limitations: URLs are deduplicated exactly, so query-parameter order or a
trailing slash creates a separate entry; JavaScript-rendered links are not
seen; `robots.txt` and crawl-delay conventions are not enforced; and there is no
rate limiting beyond sequential requests. Use it politely on sites you own or
are permitted to crawl.
