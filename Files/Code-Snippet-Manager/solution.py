#!/usr/bin/env python3
"""Store, search and export reusable code snippets in a local SQLite database.

Snippets have a title, language, comma-separated tags, an optional
description and the code itself.  The program offers add/list/search/show/
edit/delete/export commands, filters by language and tag, and can render
syntax highlighting when Pygments happens to be installed (it is optional).

``--demo`` runs a full CRUD and export cycle in a temporary database.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.environ.get("SNIPPET_DB", Path.home() / ".code_snippets.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'text',
    tags TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snippets_language ON snippets(language);
"""


class SnippetError(Exception):
    """Raised for invalid input or missing snippets."""


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_language(value: str) -> str:
    return (value or "text").strip().lower() or "text"


def normalize_tags(value: str) -> str:
    """Normalise comma/space separated tags to a deduplicated lowercase list."""
    tags: list[str] = []
    for tag in re.split(r"[,\s]+", value or ""):
        tag = tag.strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return ",".join(tags)


def tag_set(value: str) -> set[str]:
    return {tag for tag in value.split(",") if tag}


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def add_snippet(
    connection: sqlite3.Connection,
    title: str,
    code: str,
    language: str = "text",
    tags: str = "",
    description: str = "",
) -> int:
    title = title.strip()
    if not title:
        raise SnippetError("title must not be empty")
    if not code.strip():
        raise SnippetError("code must not be empty")
    stamp = now()
    cursor = connection.execute(
        "INSERT INTO snippets (title, language, tags, code, description, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, normalize_language(language), normalize_tags(tags), code,
         description.strip(), stamp, stamp),
    )
    connection.commit()
    if cursor.lastrowid is None:  # pragma: no cover - sqlite always reports it
        raise SnippetError("database did not return a new snippet id")
    return int(cursor.lastrowid)


def get_snippet(connection: sqlite3.Connection, snippet_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,)).fetchone()
    if row is None:
        raise SnippetError(f"no snippet with id {snippet_id}")
    return row


def query_snippets(
    connection: sqlite3.Connection,
    text: str = "",
    language: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM snippets WHERE 1=1"
    params: list[Any] = []
    if text:
        like = f"%{text}%"
        sql += " AND (title LIKE ? OR code LIKE ? OR description LIKE ? OR tags LIKE ?)"
        params.extend([like, like, like, like])
    if language:
        sql += " AND language = ?"
        params.append(normalize_language(language))
    sql += " ORDER BY updated DESC, id DESC"
    rows = connection.execute(sql, params).fetchall()
    if tag:
        wanted = tag.strip().lower()
        rows = [row for row in rows if wanted in tag_set(row["tags"])]
    return rows[:max(1, limit)]


def update_snippet(
    connection: sqlite3.Connection,
    snippet_id: int,
    fields: dict[str, str | None],
) -> None:
    row = get_snippet(connection, snippet_id)
    allowed = {"title", "language", "tags", "code", "description"}
    updates: dict[str, str] = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "tags":
            updates[key] = normalize_tags(value)
        elif key == "language":
            updates[key] = normalize_language(value)
        elif key in {"title", "code"}:
            if not value.strip():
                raise SnippetError(f"{key} must not be empty")
            updates[key] = value.strip() if key == "title" else value
        else:
            updates[key] = value.strip()
    if not updates:
        raise SnippetError("no fields to update")
    updates["updated"] = now()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    connection.execute(
        f"UPDATE snippets SET {assignments} WHERE id = ?",
        [*updates.values(), row["id"]],
    )
    connection.commit()


def delete_snippet(connection: sqlite3.Connection, snippet_id: int) -> None:
    cursor = connection.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
    connection.commit()
    if cursor.rowcount == 0:
        raise SnippetError(f"no snippet with id {snippet_id}")


def export_snippets(
    connection: sqlite3.Connection, path: Path, fmt: str
) -> int:
    rows = connection.execute(
        "SELECT * FROM snippets ORDER BY language, title COLLATE NOCASE"
    ).fetchall()
    if not rows:
        raise SnippetError("database has no snippets to export")
    if fmt == "json":
        payload = []
        for row in rows:
            item = dict(row)
            item["tags"] = sorted(tag_set(row["tags"]))
            payload.append(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    else:
        parts = ["# Code Snippets", ""]
        for row in rows:
            parts.append(f"## {row['title']}")
            parts.append("")
            parts.append(f"- Language: `{row['language']}`")
            if row["tags"]:
                parts.append(f"- Tags: {', '.join(sorted(tag_set(row['tags'])))}")
            parts.append(f"- Updated: {row['updated']}")
            if row["description"]:
                parts.append("")
                parts.append(row["description"])
            parts.append("")
            parts.append(f"```{row['language']}")
            parts.append(row["code"].rstrip("\n"))
            parts.append("```")
            parts.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return len(rows)


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------


def print_table(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("(no snippets)")
        return
    header = f"{'ID':>4}  {'Language':<12} {'Title':<34} {'Lines':>5}  Tags"
    print(header)
    print("-" * len(header))
    for row in rows:
        title = row["title"] if len(row["title"]) <= 34 else row["title"][:31] + "..."
        lines = row["code"].count("\n") + 1
        print(f"{row['id']:>4}  {row['language']:<12} {title:<34} {lines:>5}  {row['tags']}")


def highlight_code(code: str, language: str) -> str | None:
    """Return ANSI-highlighted code when Pygments is importable, else None."""
    try:
        from pygments import highlight
        from pygments.formatters import TerminalFormatter
        from pygments.lexers import get_lexer_by_name
    except ImportError:
        return None
    try:
        lexer = get_lexer_by_name(language)
    except Exception:
        return None
    return highlight(code, lexer, TerminalFormatter()).rstrip("\n")


def print_snippet(row: sqlite3.Row, color: bool = False) -> None:
    print(f"#{row['id']}  {row['title']}")
    print(f"Language: {row['language']}")
    print(f"Tags    : {row['tags'] or '(none)'}")
    print(f"Created : {row['created']}")
    print(f"Updated : {row['updated']}")
    if row["description"]:
        print(f"\n{row['description']}\n")
    print("-" * 60)
    rendered = highlight_code(row["code"], row["language"]) if color else None
    if rendered is not None:
        print(rendered)
        return
    for number, line in enumerate(row["code"].splitlines(), 1):
        print(f"{number:>4} | {line}")


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------

DEMO_SNIPPETS = [
    {
        "title": "Quicksort in Python",
        "language": "python",
        "tags": "algorithms, sort, recursion",
        "description": "In-place quicksort with a median-of-three pivot.",
        "code": (
            "def quicksort(items, lo=0, hi=None):\n"
            "    if hi is None:\n"
            "        hi = len(items) - 1\n"
            "    if lo >= hi:\n"
            "        return items\n"
            "    mid = (lo + hi) // 2\n"
            "    pivot = sorted((items[lo], items[mid], items[hi]))[1]\n"
            "    i, j = lo, hi\n"
            "    while i <= j:\n"
            "        while items[i] < pivot:\n"
            "            i += 1\n"
            "        while items[j] > pivot:\n"
            "            j -= 1\n"
            "        if i <= j:\n"
            "            items[i], items[j] = items[j], items[i]\n"
            "            i, j = i + 1, j - 1\n"
            "    quicksort(items, lo, j)\n"
            "    quicksort(items, i, hi)\n"
            "    return items\n"
        ),
    },
    {
        "title": "Fetch JSON with urllib",
        "language": "python",
        "tags": "web, http, json",
        "description": "Minimal GET request using only the standard library.",
        "code": (
            "import json\n"
            "import urllib.request\n\n"
            "def fetch_json(url):\n"
            "    request = urllib.request.Request(url, headers={'User-Agent': 'demo'})\n"
            "    with urllib.request.urlopen(request, timeout=10) as response:\n"
            "        return json.load(response)\n"
        ),
    },
    {
        "title": "Debounce helper",
        "language": "javascript",
        "tags": "web, frontend, timing",
        "description": "Delay a function until calls stop for `wait` milliseconds.",
        "code": (
            "export function debounce(fn, wait = 200) {\n"
            "  let timer;\n"
            "  return (...args) => {\n"
            "    clearTimeout(timer);\n"
            "    timer = setTimeout(() => fn(...args), wait);\n"
            "  };\n"
            "}\n"
        ),
    },
    {
        "title": "Recursive CTE countdown",
        "language": "sql",
        "tags": "database, sqlite, recursion",
        "description": "Generate the numbers 10 down to 1 without a table.",
        "code": (
            "WITH RECURSIVE nums(n) AS (\n"
            "  SELECT 10\n"
            "  UNION ALL\n"
            "  SELECT n - 1 FROM nums WHERE n > 1\n"
            ")\n"
            "SELECT n FROM nums;\n"
        ),
    },
]


def run_demo() -> int:
    """Exercise add, list, search, show, edit, delete and both exports."""
    with tempfile.TemporaryDirectory(prefix="snippets-") as tmp:
        work = Path(tmp)
        db_path = work / "snippets.db"
        connection = connect(db_path)
        ids = [add_snippet(connection, **item) for item in DEMO_SNIPPETS]
        # Freeze timestamps so the demonstration output is reproducible.
        connection.execute(
            "UPDATE snippets SET created = ?, updated = ?",
            ("2026-01-15T12:00:00+00:00", "2026-01-15T12:00:00+00:00"),
        )
        connection.commit()
        print(f"Created database with {len(ids)} snippets: ids={ids}")

        rows = query_snippets(connection)
        print("\nAll snippets, newest first:")
        print_table(rows)
        assert len(rows) == 4

        found = query_snippets(connection, text="quicksort")
        assert [row["id"] for row in found] == [ids[0]]
        print(f"\nText search 'quicksort' -> #{found[0]['id']} {found[0]['title']}")

        tagged = query_snippets(connection, tag="web")
        assert {row["id"] for row in tagged} == {ids[1], ids[2]}
        print(f"Tag filter 'web' -> ids {[row['id'] for row in tagged]}")

        by_lang = query_snippets(connection, language="Python")
        assert len(by_lang) == 2
        print(f"Language filter 'Python' (case-insensitive) -> {len(by_lang)} snippets")

        print("\nShow snippet #1:")
        print_snippet(get_snippet(connection, ids[0]))

        update_snippet(
            connection,
            ids[2],
            {"title": "Debounce utility", "tags": "web, timing, utility"},
        )
        edited = get_snippet(connection, ids[2])
        assert edited["title"] == "Debounce utility"
        assert tag_set(edited["tags"]) == {"web", "timing", "utility"}
        print(f"\nEdited #{ids[2]}: {edited['title']} [{edited['tags']}]")

        delete_snippet(connection, ids[3])
        assert len(query_snippets(connection)) == 3
        print(f"Deleted #{ids[3]}; 3 snippets remain")

        json_path = work / "snippets.json"
        markdown_path = work / "snippets.md"
        assert export_snippets(connection, json_path, "json") == 3
        assert export_snippets(connection, markdown_path, "markdown") == 3
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(exported) == 3 and isinstance(exported[0]["tags"], list)
        assert "## Quicksort in Python" in markdown_path.read_text(encoding="utf-8")
        print(f"Exported {len(exported)} snippets to {json_path.name} and "
              f"{markdown_path.name}")
        print(f"JSON sample keys: {sorted(exported[0])}")

        try:
            get_snippet(connection, 999)
            raise AssertionError("expected SnippetError for a missing id")
        except SnippetError:
            print("Missing-id lookup raised SnippetError as expected.")

        connection.close()
        print("\nDemo complete: CRUD, search and export work.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def read_code(args: argparse.Namespace) -> str:
    if args.code is not None:
        return args.code
    if args.code_file:
        try:
            return Path(args.code_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise SnippetError(f"cannot read code file: {exc}") from exc
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SnippetError("provide --code, --code-file, or pipe code on stdin")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Store and search code snippets in a local SQLite database.",
        epilog="Run --demo for a scripted CRUD example.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help=f"database path (default: {DEFAULT_DB})")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="add a snippet")
    add.add_argument("--title", required=True)
    add.add_argument("--language", default="text")
    add.add_argument("--tags", default="", help="comma/space separated tags")
    add.add_argument("--description", default="")
    add.add_argument("--code")
    add.add_argument("--code-file")

    listing = sub.add_parser("list", help="list snippets")
    listing.add_argument("--language")
    listing.add_argument("--tag")
    listing.add_argument("--limit", type=int, default=50)

    search = sub.add_parser("search", help="full-text search")
    search.add_argument("query")
    search.add_argument("--language")
    search.add_argument("--tag")
    search.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="print one snippet")
    show.add_argument("id", type=int)
    show.add_argument("--color", action="store_true", help="highlight with Pygments if available")

    edit = sub.add_parser("edit", help="update fields of a snippet")
    edit.add_argument("id", type=int)
    edit.add_argument("--title")
    edit.add_argument("--language")
    edit.add_argument("--tags")
    edit.add_argument("--description")
    edit.add_argument("--code")
    edit.add_argument("--code-file")

    delete = sub.add_parser("delete", help="delete a snippet")
    delete.add_argument("id", type=int)
    delete.add_argument("--yes", action="store_true", help="skip confirmation")

    export = sub.add_parser("export", help="export all snippets")
    export.add_argument("path", type=Path)
    export.add_argument("--format", choices=["json", "markdown"], default="json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.command:
        parser.print_help()
        return 0

    try:
        connection = connect(args.db)
        if args.command == "add":
            snippet_id = add_snippet(
                connection,
                title=args.title,
                code=read_code(args),
                language=args.language,
                tags=args.tags,
                description=args.description,
            )
            print(f"Added snippet #{snippet_id}: {args.title}")
        elif args.command == "list":
            print_table(query_snippets(connection, language=args.language,
                                       tag=args.tag, limit=args.limit))
        elif args.command == "search":
            print_table(query_snippets(connection, text=args.query, language=args.language,
                                       tag=args.tag, limit=args.limit))
        elif args.command == "show":
            print_snippet(get_snippet(connection, args.id), color=args.color)
        elif args.command == "edit":
            fields = {
                "title": args.title,
                "language": args.language,
                "tags": args.tags,
                "description": args.description,
                "code": read_code(args) if (args.code is not None or args.code_file) else None,
            }
            update_snippet(connection, args.id, fields)
            print(f"Updated snippet #{args.id}")
        elif args.command == "delete":
            get_snippet(connection, args.id)
            if not args.yes:
                if not sys.stdin.isatty():
                    print("error: use --yes when stdin is not a terminal", file=sys.stderr)
                    return 2
                answer = input(f"Delete snippet #{args.id}? [y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    print("Cancelled.")
                    return 0
            delete_snippet(connection, args.id)
            print(f"Deleted snippet #{args.id}")
        elif args.command == "export":
            count = export_snippets(connection, args.path, args.format)
            print(f"Exported {count} snippets to {args.path} ({args.format})")
        connection.close()
        return 0
    except SnippetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
