#!/usr/bin/env python3
"""A small line-oriented text editor with an optional curses full-screen mode.

The editor keeps a list of lines in memory and exposes a small command
language (open, view, insert, append, delete, replace, find, undo, save).
It works in any terminal, and ``--demo`` drives the same commands against
temporary files without user input.  A curses TUI is available with ``--tui``
on a real terminal.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import tempfile
from pathlib import Path

MAX_UNDO = 100


class Editor:
    """In-memory line buffer with a small undo history."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.path: Path | None = None
        self.modified = False
        self._undo: list[list[str]] = []

    # -- persistence -----------------------------------------------------
    def load(self, path: str | Path) -> int:
        """Load *path* into the buffer and return the number of lines."""
        p = Path(path).expanduser()
        text = p.read_text(encoding="utf-8")
        self.lines = text.splitlines()
        self.path = p
        self.modified = False
        self._undo.clear()
        return len(self.lines)

    def save(self, path: str | Path | None = None) -> Path:
        """Write the buffer to *path* (or the current path)."""
        target = Path(path).expanduser() if path else self.path
        if target is None:
            raise ValueError("no filename given; use 'save <path>'")
        target.write_text("\n".join(self.lines) + ("\n" if self.lines else ""), encoding="utf-8")
        self.path = target
        self.modified = False
        return target

    # -- editing ---------------------------------------------------------
    def _snapshot(self) -> None:
        self._undo.append(list(self.lines))
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)

    def _index(self, lineno: int, allow_end: bool = False) -> int:
        upper = len(self.lines) + (1 if allow_end else 0)
        if not 1 <= lineno <= upper:
            raise IndexError(f"line {lineno} is out of range (1-{upper})")
        return lineno - 1

    def insert(self, lineno: int, text: str) -> None:
        """Insert *text* before 1-based *lineno* (lineno may be len+1)."""
        self._snapshot()
        self.lines.insert(self._index(lineno, allow_end=True), text)
        self.modified = True

    def append(self, text: str) -> int:
        """Append a line at the end and return its 1-based number."""
        self._snapshot()
        self.lines.append(text)
        self.modified = True
        return len(self.lines)

    def delete(self, start: int, end: int | None = None) -> int:
        """Delete one line or an inclusive range; return the number removed."""
        end = start if end is None else end
        self._index(start)
        self._index(end)
        if end < start:
            start, end = end, start
        self._snapshot()
        removed = len(self.lines[start - 1:end])
        del self.lines[start - 1:end]
        self.modified = True
        return removed

    def replace(self, lineno: int, text: str) -> None:
        self._snapshot()
        self.lines[self._index(lineno)] = text
        self.modified = True

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.lines = self._undo.pop()
        self.modified = True
        return True

    # -- views -----------------------------------------------------------
    def view(self, start: int | None = None, end: int | None = None) -> str:
        if not self.lines:
            return "(empty buffer)"
        start = 1 if start is None else max(1, start)
        end = len(self.lines) if end is None else min(len(self.lines), end)
        if start > end:
            return "(empty range)"
        width = len(str(len(self.lines)))
        return "\n".join(
            f"{n:>{width}} | {self.lines[n - 1]}" for n in range(start, end + 1)
        )

    def find(self, needle: str) -> list[tuple[int, str]]:
        low = needle.casefold()
        return [(i, line) for i, line in enumerate(self.lines, 1) if low in line.casefold()]


def _parse_range(token: str, total: int) -> tuple[int, int]:
    """Parse ``N`` or ``N-M`` into a 1-based inclusive range."""
    if "-" in token:
        first, _, last = token.partition("-")
        start, end = int(first), int(last)
    else:
        start = end = int(token)
    if start > end:
        start, end = end, start
    if start < 1 or end > total:
        raise ValueError(f"range must be within 1-{total}")
    return start, end


class CommandError(Exception):
    """Raised for malformed editor commands."""


def execute(editor: Editor, command: str) -> tuple[bool, str]:
    """Run one editor command; return ``(keep_running, output)``."""
    stripped = command.strip()
    if not stripped:
        return True, ""
    verb = stripped.split(maxsplit=1)[0].lower()

    # Text-bearing commands are parsed raw so apostrophes, quotes, and runs of
    # spaces are kept literally instead of being interpreted by shlex.
    if verb in {"insert", "replace"}:
        match = re.match(r"^\S+\s+(\d+)\s+(.*)$", stripped, re.S)
        if not match:
            raise CommandError(f"usage: {verb} <line> <text>")
        try:
            if verb == "insert":
                editor.insert(int(match.group(1)), match.group(2))
            else:
                editor.replace(int(match.group(1)), match.group(2))
        except (ValueError, IndexError) as exc:
            raise CommandError(str(exc)) from exc
        return True, f"{'Inserted before' if verb == 'insert' else 'Replaced'} line {match.group(1)}."
    if verb in {"append", "find"}:
        match = re.match(r"^\S+\s+(.*)$", stripped, re.S)
        if not match or not match.group(1):
            raise CommandError(f"usage: {verb} <text>")
        if verb == "append":
            number = editor.append(match.group(1))
            return True, f"Appended line {number}."
        hits = editor.find(match.group(1))
        if not hits:
            return True, "No matches."
        return True, "\n".join(f"{n}: {line}" for n, line in hits)

    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        raise CommandError(f"cannot parse command: {exc}") from exc
    args = parts[1:]

    if verb in {"quit", "exit"}:
        if editor.modified:
            return False, "Exiting with unsaved changes."
        return False, "Bye."
    if verb == "help":
        return True, COMMAND_HELP
    if verb == "open":
        if not args:
            raise CommandError("usage: open <path>")
        try:
            count = editor.load(args[0])
        except (OSError, UnicodeDecodeError) as exc:
            raise CommandError(f"cannot open {args[0]}: {exc}") from exc
        return True, f"Opened {editor.path} ({count} lines)."
    if verb == "view":
        if args:
            try:
                start, end = _parse_range(args[0], max(1, len(editor.lines)))
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            return True, editor.view(start, end)
        return True, editor.view()
    if verb == "delete":
        if not args:
            raise CommandError("usage: delete <line|start-end>")
        try:
            if "-" in args[0]:
                start, end = _parse_range(args[0], len(editor.lines))
            else:
                start = end = int(args[0])
                editor._index(start)
            removed = editor.delete(start, end)
        except (ValueError, IndexError) as exc:
            raise CommandError(str(exc)) from exc
        return True, f"Deleted {removed} line(s)."
    if verb == "undo":
        return True, "Undone." if editor.undo() else "Nothing to undo."
    if verb == "save":
        try:
            target = editor.save(args[0] if args else None)
        except (OSError, ValueError) as exc:
            raise CommandError(f"cannot save: {exc}") from exc
        return True, f"Saved {len(editor.lines)} lines to {target}."
    if verb == "lines":
        return True, f"{len(editor.lines)} line(s); {'modified' if editor.modified else 'saved'}."
    raise CommandError(f"unknown command '{verb}' (try 'help')")


COMMAND_HELP = """Commands:
  open <path>              load a file
  view [start[-end]]       show numbered lines
  insert <line> <text>     insert text before a line (len+1 appends)
  append <text>            add a line at the end
  delete <line|start-end>  remove one line or an inclusive range
  replace <line> <text>    replace a whole line
  find <text>              case-insensitive substring search
  undo                     restore the previous buffer state
  save [path]              write the buffer to disk
  lines                    show line count and dirty flag
  quit                     leave the editor"""


def interactive(editor: Editor) -> int:
    """Read commands from a terminal until EOF or ``quit``."""
    if editor.path:
        print(f"Editing {editor.path} ({len(editor.lines)} lines). Type 'help' for commands.")
    else:
        print("Empty buffer. Type 'open <file>' or 'help'.")
    while True:
        try:
            raw = input("editor> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            keep_running, output = execute(editor, raw)
        except CommandError as exc:
            print(f"error: {exc}")
            continue
        if output:
            print(output)
        if not keep_running:
            break
    return 0


# -- curses front-end ----------------------------------------------------
def run_tui(path: Path) -> int:
    """Minimal full-screen editor: arrows, typing, Ctrl-S save, Ctrl-Q quit."""
    try:
        import curses
    except ImportError:
        print("curses is not available on this Python build.", file=sys.stderr)
        return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("--tui needs an interactive terminal.", file=sys.stderr)
        return 2

    editor = Editor()
    if path.exists():
        editor.load(path)
    else:
        editor.path = path
        editor.lines = [""]

    def loop(screen) -> None:
        curses.curs_set(1)
        row = col = top = 0
        while True:
            height, width = screen.getmaxyx()
            body = height - 1
            top = max(0, min(top, max(0, len(editor.lines) - body)))
            if row < top:
                top = row
            elif row >= top + body:
                top = row - body + 1
            screen.erase()
            for offset in range(body):
                index = top + offset
                if index >= len(editor.lines):
                    break
                screen.addnstr(offset, 0, editor.lines[index], max(0, width - 1))
            status = f" {editor.path.name if editor.path else '[No Name]'}"
            status += " *" if editor.modified else ""
            status += f"  Ln {row + 1}, Col {col + 1}  ^S save  ^Q quit"
            screen.addnstr(height - 1, 0, status.ljust(width - 1), max(0, width - 1),
                           curses.A_REVERSE)
            screen.move(row - top, min(col, max(0, width - 2)))
            screen.refresh()

            key = screen.getch()
            line = editor.lines[row] if row < len(editor.lines) else ""
            if key in (17,):  # Ctrl-Q
                return
            if key == 19:  # Ctrl-S
                if editor.path is None:
                    editor.path = path
                editor.save()
                continue
            if key == curses.KEY_UP:
                row = max(0, row - 1)
                col = min(col, len(editor.lines[row]))
            elif key == curses.KEY_DOWN:
                row = min(len(editor.lines) - 1, row + 1)
                col = min(col, len(editor.lines[row]))
            elif key == curses.KEY_LEFT:
                if col > 0:
                    col -= 1
                elif row > 0:
                    row -= 1
                    col = len(editor.lines[row])
            elif key == curses.KEY_RIGHT:
                if col < len(line):
                    col += 1
                elif row < len(editor.lines) - 1:
                    row += 1
                    col = 0
            elif key in (curses.KEY_BACKSPACE, 8, 127):
                editor._snapshot()
                if col > 0:
                    editor.lines[row] = line[:col - 1] + line[col:]
                    col -= 1
                elif row > 0:
                    prev = editor.lines[row - 1]
                    col = len(prev)
                    editor.lines[row - 1] = prev + line
                    del editor.lines[row]
                    row -= 1
                editor.modified = True
            elif key in (10, 13, curses.KEY_ENTER):
                editor._snapshot()
                editor.lines[row:row + 1] = [line[:col], line[col:]]
                row += 1
                col = 0
                editor.modified = True
            elif 32 <= key <= 126:
                editor._snapshot()
                editor.lines[row] = line[:col] + chr(key) + line[col:]
                col += 1
                editor.modified = True
            elif key == curses.KEY_RESIZE:
                continue

    try:
        curses.wrapper(loop)
    except KeyboardInterrupt:
        pass
    if editor.modified:
        try:
            editor.save()
            print(f"Saved {editor.path}.")
        except OSError as exc:
            print(f"Could not save: {exc}", file=sys.stderr)
            return 1
    return 0


# -- demo ----------------------------------------------------------------
def demo() -> int:
    """Scripted session against temporary files; no input required."""
    import os

    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = Path.cwd()
        os.chdir(tmp)
        try:
            source = Path("notes.txt")
            source.write_text(
                "Shopping list\nmilk\neggs\nbread\ncall the plumber\n", encoding="utf-8"
            )
            target = Path("edited.txt")
            editor = Editor()
            script = [
                "open notes.txt",
                "view",
                "replace 2 oat milk",
                "insert 5 a new line before the plumber",
                "delete 3",
                "append buy stamps",
                "find milk",
                "save edited.txt",
                "lines",
            ]
            print("Text Editor demo\n" + "=" * 16)
            for command in script:
                keep_running, output = execute(editor, command)
                print(f"\neditor> {command}")
                if output:
                    print(output)
                if not keep_running:
                    break
            print("\n--- saved file ---")
            print(target.read_text(encoding="utf-8"), end="")
            expected = (
                "Shopping list\noat milk\nbread\na new line before the plumber\n"
                "call the plumber\nbuy stamps\n"
            )
            if target.read_text(encoding="utf-8") != expected:
                print("demo assertion failed: unexpected file contents", file=sys.stderr)
                return 1
            print("demo assertion passed: file contents match the scripted edits")
        finally:
            os.chdir(old_cwd)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A command-driven line editor with an optional curses TUI.",
        epilog="Commands: open, view, insert, append, delete, replace, find, undo, save.",
    )
    parser.add_argument("file", nargs="?", help="file to open at startup")
    parser.add_argument("--tui", action="store_true", help="use the curses full-screen editor")
    parser.add_argument("--demo", action="store_true", help="run a scripted, non-interactive demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return demo()
    if args.tui:
        if not args.file:
            print("--tui requires a filename.", file=sys.stderr)
            return 2
        return run_tui(Path(args.file).expanduser())
    editor = Editor()
    if args.file:
        try:
            count = editor.load(args.file)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"cannot open {args.file}: {exc}", file=sys.stderr)
            return 1
        print(f"Opened {editor.path} ({count} lines).")
    if not sys.stdin.isatty():
        print("No terminal available. Use --demo for a scripted demonstration.", file=sys.stderr)
        return 2
    return interactive(editor)


if __name__ == "__main__":
    raise SystemExit(main())
