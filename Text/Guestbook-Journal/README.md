# Guestbook / Journal

*Category: Text · Project directory: `Text/Guestbook-Journal/`*

## Problem

A simple application that allows people to add comments or write journal entries. It can allow comments or not and timestamps for all entries.

## Features

- SQLite storage for entries and comments, with UTC timestamps.
- Entries record an author, body, creation time, and whether comments are open.
- Comment threads with their own author and timestamp.
- List entries newest-first with comment counts.
- View one entry with all of its comments.
- Case-insensitive search over entry bodies and authors.
- Delete an entry and its comments (foreign-key cascade).
- Interactive `guestbook>` shell when run with no subcommand on a terminal.
- `--demo` exercises the whole flow against a temporary database.

## Requirements

Python 3.10+ (standard library only: `sqlite3`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --db journal.db add --author Ada --body "First entry."
python3 solution.py --db journal.db add --author Grace --body "No comments here." --no-comments
python3 solution.py --db journal.db list
python3 solution.py --db journal.db view 1
python3 solution.py --db journal.db comment 1 --author Bob --body "Nice start."
python3 solution.py --db journal.db search parser
python3 solution.py --db journal.db delete 2 --yes
python3 solution.py --db journal.db        # interactive shell
```

Global options (`--db`, `--demo`) go before the subcommand.

| Option / command | Meaning |
| --- | --- |
| `--db PATH` | Database file (default `guestbook.db`). |
| `add --body TEXT [--author NAME] [--no-comments]` | Create an entry; comments are allowed by default. |
| `list` | Show entries, newest first, with comment status. |
| `view ID` | Show one entry and its comments. |
| `comment ID --body TEXT [--author NAME]` | Add a comment if the entry allows it. |
| `search TERM` | Search bodies and authors. |
| `delete ID [--yes]` | Delete an entry and its comments; prompts without `--yes`. |
| `--demo` | Run the scripted demo against a temporary database. |

## Example Output

```text
Guestbook / Journal demo
==========================
Added entries #1, #2, #3 and 2 comments.

expected refusal: comments are disabled for entry 2

--- all entries (newest first) ---
#3   2026-11-02 18:51 UTC  Linus        [1 comment(s)]
     Quiet evening. Read a chapter of Cryptonomicon.
#2   2026-11-02 18:51 UTC  Grace        [comments off]
     Debugging note: the parser drops trailing spaces.
#1   2026-11-02 18:51 UTC  Ada          [1 comment(s)]
     Shipped the guestbook schema today.

--- entry #1 with comments ---
Entry #1 — Ada — 2026-11-02 18:51 UTC
Comments: allowed

Shipped the guestbook schema today.

Comments (1):
  - Bob at 2026-11-02 18:51 UTC: Congratulations! The timestamp column looks right.
```

## Implementation Notes

- Two tables: `entries` and `comments`, with `comments.entry_id` a foreign key using `ON DELETE CASCADE`. `PRAGMA foreign_keys = ON` is set on every connection so deleting an entry also removes its comments.
- Timestamps are stored as ISO 8601 UTC (`datetime.now(timezone.utc).isoformat`) and rendered as `YYYY-MM-DD HH:MM UTC`.
- `add_comment` checks both existence and the entry's `allow_comments` flag, raising a clear error for a closed entry.
- Search uses SQLite `instr(lower(...))` over body and author, so `%` and `_` in the term are literal; case folding is ASCII-only, which suits SQLite's built-in `lower()`.
- The schema is created on startup with `CREATE TABLE IF NOT EXISTS`, so the database file can be new or existing.
- The demo creates a fresh temporary database, asserts the search hit and cascade delete, then removes it. No existing database is touched.
