# Code Snippet Manager

Category: `Files` · Project: `Code-Snippet-Manager`

## Problem

A utility program that allows coders to store functions, classes or other
tidbits to save for later, organized by the type of snippet or language.

## Features

- SQLite storage — one portable database file, no server.
- Add snippets with title, language, tags, description and code
  (`--code`, `--code-file`, or piped stdin).
- List snippets newest-first, filtered by language and tag.
- Full-text search across title, code, description and tags.
- Show a snippet with line numbers; optional ANSI syntax highlighting when
  Pygments is already installed.
- Edit any field, preserving the original creation timestamp.
- Delete with confirmation (`--yes` to skip).
- Export everything to JSON (tags as arrays) or GitHub-flavored Markdown.
- `--demo` runs a complete add/list/search/show/edit/delete/export cycle in a
  temporary database.

## Requirements

Python 3.10+ and the standard library only (`sqlite3`, `json`, `argparse`).

Optional: [Pygments](https://pygments.org/) for `show --color`. It is detected
at runtime; nothing needs to be installed for normal use.

## Usage

```bash
# Add a snippet from a file
python3 solution.py --db snippets.db add --title "Quicksort" \
    --language python --tags "algorithms,sort" \
    --description "In-place quicksort" --code-file quicksort.py

# Add from a shell string
python3 solution.py --db snippets.db add --title "Debounce" --language javascript \
    --tags "web,timing" --code "const f = () => {};"

# List and filter
python3 solution.py --db snippets.db list
python3 solution.py --db snippets.db list --language python --tag sort

# Search, show (with optional colour), edit, delete
python3 solution.py --db snippets.db search "pivot"
python3 solution.py --db snippets.db show 1 --color
python3 solution.py --db snippets.db edit 1 --tags "algorithms,sorting,recursion"
python3 solution.py --db snippets.db delete 1 --yes

# Export
python3 solution.py --db snippets.db export snippets.json --format json
python3 solution.py --db snippets.db export snippets.md --format markdown

# Scripted demonstration
python3 solution.py --demo
```

The database defaults to `~/.code_snippets.db`; override it with `--db` or the
`SNIPPET_DB` environment variable.

### Commands

| Command | Purpose |
| --- | --- |
| `add` | `--title` (required), `--language`, `--tags`, `--description`, `--code` / `--code-file` |
| `list` | `--language`, `--tag`, `--limit` |
| `search QUERY` | Same filters as `list` |
| `show ID` | `--color` for Pygments output |
| `edit ID` | Any of `--title`, `--language`, `--tags`, `--description`, `--code`, `--code-file` |
| `delete ID` | `--yes` skips the prompt |
| `export PATH` | `--format json` or `--format markdown` |

## Example Output

```
Created database with 4 snippets: ids=[1, 2, 3, 4]

All snippets, newest first:
  ID  Language     Title                              Lines  Tags
-----------------------------------------------------------------
   4  sql          Recursive CTE countdown                7  database,sqlite,recursion
   3  javascript   Debounce helper                        8  web,frontend,timing
   2  python       Fetch JSON with urllib                 8  web,http,json
   1  python       Quicksort in Python                   20  algorithms,sort,recursion

Text search 'quicksort' -> #1 Quicksort in Python
Tag filter 'web' -> ids [3, 2]
Language filter 'Python' (case-insensitive) -> 2 snippets

Show snippet #1:
#1  Quicksort in Python
Language: python
Tags    : algorithms,sort,recursion
Created : 2026-01-15T12:00:00+00:00
Updated : 2026-01-15T12:00:00+00:00

In-place quicksort with a median-of-three pivot.

------------------------------------------------------------
   1 | def quicksort(items, lo=0, hi=None):
   2 |     if hi is None:
...

Edited #3: Debounce utility [web,timing,utility]
Deleted #4; 3 snippets remain
Exported 3 snippets to snippets.json and snippets.md

Demo complete: CRUD, search and export work.
```

## Implementation Notes

- Schema: `snippets(id, title, language, tags, code, description, created,
  updated)` with an index on `language`. `created`/`updated` are ISO-8601 UTC
  strings; edits only change `updated`.
- Tags are normalised to a deduplicated lowercase comma-separated list (commas
  and whitespace both separate tags). Tag filtering happens in Python after the
  SQL filter because the list is small; language and text filters use SQL.
- Search uses `LIKE '%query%'` across title, code, description and tags, which
  is simple and portable but not a full-text index.
- Export ordering is language then case-insensitive title, so the output is
  deterministic. JSON stores tags as arrays; Markdown uses fenced code blocks
  tagged with the snippet language.
- Pygments is imported lazily only for `show --color`; if absent, the command
  prints plain numbered source and never fails.
- Limitations: no syntax-aware storage, no version history, no concurrent
  multi-user locking beyond SQLite's own, and `LIKE` search is not tokenised
  (a search for "sort" will also match "resorter").
