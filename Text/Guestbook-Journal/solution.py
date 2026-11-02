#!/usr/bin/env python3
"""A SQLite-backed guestbook and journal with timestamps and optional comments.

Each entry records an author, body, and UTC creation time.  Entries can allow
comments or be closed to them; comments carry their own author and timestamp.
The CLI supports add/list/view/comment/search/delete, and ``--demo`` exercises
all of it against a temporary database.
"""

from __future__ import annotations

import argparse
import shlex
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    author         TEXT NOT NULL,
    body           TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    allow_comments INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id   INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    author     TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_entry ON comments(entry_id);
"""


class GuestbookError(Exception):
    """Raised for user-facing guestbook problems."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_time(raw: str) -> str:
    """Render an ISO timestamp as ``YYYY-MM-DD HH:MM UTC``."""
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return raw


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def add_entry(conn: sqlite3.Connection, body: str, author: str = "Anonymous",
              allow_comments: bool = True) -> int:
    body, author = body.strip(), (author.strip() or "Anonymous")
    if not body:
        raise GuestbookError("an entry needs a non-empty body")
    cursor = conn.execute(
        "INSERT INTO entries (author, body, created_at, allow_comments) VALUES (?, ?, ?, ?)",
        (author, body, utc_now(), int(allow_comments)),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise GuestbookError("database did not assign an entry id")
    return int(cursor.lastrowid)


def get_entry(conn: sqlite3.Connection, entry_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT e.*, (SELECT COUNT(*) FROM comments c WHERE c.entry_id = e.id) AS comment_count "
        "FROM entries e WHERE e.id = ?",
        (entry_id,),
    ).fetchone()


def add_comment(conn: sqlite3.Connection, entry_id: int, body: str,
                author: str = "Anonymous") -> int:
    entry = get_entry(conn, entry_id)
    if entry is None:
        raise GuestbookError(f"entry {entry_id} does not exist")
    if not entry["allow_comments"]:
        raise GuestbookError(f"comments are disabled for entry {entry_id}")
    body, author = body.strip(), (author.strip() or "Anonymous")
    if not body:
        raise GuestbookError("a comment needs a non-empty body")
    cursor = conn.execute(
        "INSERT INTO comments (entry_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, author, body, utc_now()),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise GuestbookError("database did not assign a comment id")
    return int(cursor.lastrowid)


def list_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT e.*, (SELECT COUNT(*) FROM comments c WHERE c.entry_id = e.id) AS comment_count "
        "FROM entries e ORDER BY e.id DESC"
    ).fetchall()


def get_comments(conn: sqlite3.Connection, entry_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM comments WHERE entry_id = ? ORDER BY id", (entry_id,)
    ).fetchall()


def search_entries(conn: sqlite3.Connection, term: str) -> list[sqlite3.Row]:
    pattern = term.strip().lower()
    if not pattern:
        raise GuestbookError("search term must not be empty")
    return conn.execute(
        "SELECT e.*, (SELECT COUNT(*) FROM comments c WHERE c.entry_id = e.id) AS comment_count "
        "FROM entries e WHERE instr(lower(e.body), ?) > 0 OR instr(lower(e.author), ?) > 0 "
        "ORDER BY e.id DESC",
        (pattern, pattern),
    ).fetchall()


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> bool:
    cursor = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    return cursor.rowcount > 0


def render_list(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "(no entries yet)"
    lines = []
    for row in rows:
        state = f"{row['comment_count']} comment(s)" if row["allow_comments"] else "comments off"
        lines.append(
            f"#{row['id']:<3} {format_time(row['created_at'])}  {row['author']:<12} [{state}]"
        )
        lines.append(f"     {row['body']}")
    return "\n".join(lines)


def render_entry(conn: sqlite3.Connection, entry_id: int) -> str:
    entry = get_entry(conn, entry_id)
    if entry is None:
        raise GuestbookError(f"entry {entry_id} does not exist")
    lines = [
        f"Entry #{entry['id']} — {entry['author']} — {format_time(entry['created_at'])}",
        f"Comments: {'allowed' if entry['allow_comments'] else 'disabled'}",
        "",
        entry["body"],
    ]
    comments = get_comments(conn, entry_id)
    lines.append("")
    lines.append(f"Comments ({len(comments)}):")
    if not comments:
        lines.append("  (none)")
    for comment in comments:
        lines.append(f"  - {comment['author']} at {format_time(comment['created_at'])}: {comment['body']}")
    return "\n".join(lines)


def prompt_multiline(label: str) -> str:
    print(f"{label} (finish with a single '.'):")
    lines = []
    while True:
        line = input("> ")
        if line == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def interactive(conn: sqlite3.Connection) -> int:
    """Small menu-style shell for use on a terminal."""
    print("Guestbook / Journal — type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            raw = input("guestbook> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"error: {exc}")
            continue
        if not parts:
            continue
        verb, args = parts[0].lower(), parts[1:]
        try:
            if verb in {"quit", "exit"}:
                return 0
            if verb == "help":
                print("add, list, view <id>, comment <id>, search <term>, delete <id>, quit")
            elif verb == "add":
                author = input("Author [Anonymous]: ").strip() or "Anonymous"
                body = prompt_multiline("Entry")
                allow = input("Allow comments? [Y/n]: ").strip().lower() not in {"n", "no"}
                print(f"Added entry #{add_entry(conn, body, author, allow)}.")
            elif verb == "list":
                print(render_list(list_entries(conn)))
            elif verb == "view" and args:
                print(render_entry(conn, int(args[0])))
            elif verb == "comment" and args:
                author = input("Author [Anonymous]: ").strip() or "Anonymous"
                body = prompt_multiline("Comment")
                print(f"Added comment #{add_comment(conn, int(args[0]), body, author)}.")
            elif verb == "search" and args:
                print(render_list(search_entries(conn, " ".join(args))))
            elif verb == "delete" and args:
                print("Deleted." if delete_entry(conn, int(args[0])) else "No such entry.")
            else:
                print("error: unknown or incomplete command (try 'help')")
        except (GuestbookError, ValueError) as exc:
            print(f"error: {exc}")


def demo() -> int:
    """Exercise entries, comments, search, and deletion against a temp database."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "demo.db"
        conn = connect(db_path)
        init_db(conn)
        print("Guestbook / Journal demo\n" + "=" * 26)

        first = add_entry(conn, "Shipped the guestbook schema today.", "Ada")
        second = add_entry(conn, "Debugging note: the parser drops trailing spaces.", "Grace",
                           allow_comments=False)
        third = add_entry(conn, "Quiet evening. Read a chapter of Cryptonomicon.", "Linus")
        add_comment(conn, first, "Congratulations! The timestamp column looks right.", "Bob")
        add_comment(conn, third, "That book is on my list.", "Ada")
        print(f"Added entries #{first}, #{second}, #{third} and 2 comments.\n")
        try:
            add_comment(conn, second, "Should be rejected.", "Mallory")
        except GuestbookError as exc:
            print(f"expected refusal: {exc}\n")

        print("--- all entries (newest first) ---")
        print(render_list(list_entries(conn)))
        print("\n--- entry #1 with comments ---")
        print(render_entry(conn, first))
        print("\n--- search: 'parser' ---")
        hits = search_entries(conn, "parser")
        print(render_list(hits))
        print("\n--- delete entry #2 ---")
        print("deleted" if delete_entry(conn, second) else "not found")
        print("\n--- after deletion ---")
        print(render_list(list_entries(conn)))

        remaining = list_entries(conn)
        if len(remaining) != 2 or get_entry(conn, second) is not None:
            print("demo assertion failed: delete did not remove the entry", file=sys.stderr)
            return 1
        entry = get_entry(conn, first)
        if entry is None or entry["comment_count"] != 1:
            print("demo assertion failed: comment count is wrong", file=sys.stderr)
            return 1
        if len(hits) != 1 or hits[0]["id"] != second:
            print("demo assertion failed: search returned the wrong row", file=sys.stderr)
            return 1
        conn.close()
        print("\ndemo assertions passed: 3 entries, 2 comments, search and cascade delete work")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A SQLite guestbook/journal with timestamps and optional comments.",
    )
    parser.add_argument("--db", default="guestbook.db", metavar="PATH",
                        help="database file (default: guestbook.db)")
    parser.add_argument("--demo", action="store_true", help="run against a temporary demo database")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="write a new entry")
    add.add_argument("--author", default="Anonymous")
    add.add_argument("--body", required=True)
    add.add_argument("--no-comments", action="store_true", help="close the entry to comments")

    sub.add_parser("list", help="list entries, newest first")

    view = sub.add_parser("view", help="show an entry and its comments")
    view.add_argument("id", type=int)

    comment = sub.add_parser("comment", help="comment on an entry")
    comment.add_argument("id", type=int)
    comment.add_argument("--author", default="Anonymous")
    comment.add_argument("--body", required=True)

    search = sub.add_parser("search", help="search entry text and authors")
    search.add_argument("term")

    delete = sub.add_parser("delete", help="delete an entry (and its comments)")
    delete.add_argument("id", type=int)
    delete.add_argument("--yes", action="store_true", help="skip the confirmation prompt")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return demo()

    db_path = Path(args.db).expanduser()
    try:
        conn = connect(db_path)
        init_db(conn)
    except (sqlite3.Error, OSError) as exc:
        print(f"error: cannot open database {db_path}: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "add":
            entry_id = add_entry(conn, args.body, args.author, not args.no_comments)
            print(f"Added entry #{entry_id}.")
        elif args.command == "list":
            print(render_list(list_entries(conn)))
        elif args.command == "view":
            print(render_entry(conn, args.id))
        elif args.command == "comment":
            comment_id = add_comment(conn, args.id, args.body, args.author)
            print(f"Added comment #{comment_id} to entry #{args.id}.")
        elif args.command == "search":
            print(render_list(search_entries(conn, args.term)))
        elif args.command == "delete":
            if not args.yes:
                if not sys.stdin.isatty():
                    print("error: use --yes to delete without a terminal prompt", file=sys.stderr)
                    return 2
                confirm = input(f"Delete entry #{args.id} and its comments? [y/N] ")
                if confirm.strip().lower() not in {"y", "yes"}:
                    print("Cancelled.")
                    return 0
            print("Deleted." if delete_entry(conn, args.id) else f"Entry #{args.id} not found.")
        else:
            if not sys.stdin.isatty():
                parser.print_usage(sys.stderr)
                print("error: a command is required (or use --demo)", file=sys.stderr)
                return 2
            interactive(conn)
    except (GuestbookError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
