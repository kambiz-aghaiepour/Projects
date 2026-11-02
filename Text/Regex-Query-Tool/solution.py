#!/usr/bin/env python3
"""Run a regular expression against source text and explain the results.

Shows every match with its span, numbered and named capture groups, and a
short context line.  Invalid patterns are reported with the parser's message
and position instead of a traceback.  Optional replacement uses Python's
``re.sub`` syntax (``\\1``, ``\\g<name>``).  ``--demo`` runs sample queries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_TEXT = """\
2024-05-01 12:00:01 INFO  user=ada email=ada@example.com id=42
2024-05-01 12:00:05 WARN  user=grace email=grace@example.org id=7
2024-05-01 12:00:09 ERROR user=linus email=linus@example.net id=99
2024-05-01 12:00:12 INFO  user=ada email=ada@example.com id=43
"""


class RegexError(Exception):
    """Raised when a pattern or replacement is invalid."""


@dataclass
class MatchRecord:
    """A serializable summary of one ``re.Match``."""

    number: int
    text: str
    start: int
    end: int
    groups: list[tuple[int, str | None]] = field(default_factory=list)
    named_groups: dict[str, str | None] = field(default_factory=dict)
    context: str = ""

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "text": self.text,
            "span": [self.start, self.end],
            "groups": {str(index): value for index, value in self.groups},
            "named_groups": self.named_groups,
            "context": self.context,
        }


def compile_pattern(pattern: str, ignore_case: bool = False, multiline: bool = False,
                    dotall: bool = False) -> re.Pattern[str]:
    """Compile *pattern*, translating ``re.error`` into a readable message."""
    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    if dotall:
        flags |= re.DOTALL
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        position = f" at position {exc.pos}" if exc.pos is not None else ""
        raise RegexError(f"{exc.msg}{position}") from exc


def flag_names(flags: int) -> list[str]:
    names = []
    for value, name in ((re.IGNORECASE, "IGNORECASE"), (re.MULTILINE, "MULTILINE"),
                        (re.DOTALL, "DOTALL")):
        if flags & value:
            names.append(name)
    return names


def line_context(text: str, start: int, end: int, width: int = 100) -> str:
    """Return the line around a match with the matched text in square brackets."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    prefix, matched, suffix = text[line_start:start], text[start:end], text[end:line_end]
    if len(prefix) > width:
        prefix = "…" + prefix[-width:]
    if len(suffix) > width:
        suffix = suffix[:width] + "…"
    if len(matched) > 80:
        matched = matched[:77] + "…"
    display = matched.replace("\n", "\\n")
    return f"{prefix}[{display}]{suffix}"


def collect_matches(rx: re.Pattern[str], text: str) -> list[MatchRecord]:
    """Collect every non-overlapping match with groups and context."""
    records = []
    for number, match in enumerate(rx.finditer(text), 1):
        records.append(MatchRecord(
            number=number,
            text=match.group(0),
            start=match.start(),
            end=match.end(),
            groups=[(index, match.group(index)) for index in range(1, rx.groups + 1)],
            named_groups={name: match.group(name) for name in rx.groupindex},
            context=line_context(text, match.start(), match.end()),
        ))
    return records


def render_matches(pattern: str, rx: re.Pattern[str], records: list[MatchRecord],
                   total_chars: int) -> str:
    """Human-readable match report."""
    flags = ", ".join(flag_names(rx.flags)) or "none"
    lines = [
        f"Pattern: {pattern}",
        f"Flags:   {flags}",
        f"Matches: {len(records)} in {total_chars} character(s)",
    ]
    if not records:
        lines.append("(no matches)")
        return "\n".join(lines)
    for record in records:
        lines.append("")
        shown = record.text.replace("\n", "\\n")
        lines.append(f"[{record.number}] {shown!r}  span=({record.start}, {record.end})")
        if record.groups:
            values = ", ".join(f"{index}={value!r}" for index, value in record.groups)
            lines.append(f"    groups: {values}")
        if record.named_groups:
            values = ", ".join(f"{name}={value!r}" for name, value in record.named_groups.items())
            lines.append(f"    named:  {values}")
        lines.append(f"    line:   {record.context}")
    return "\n".join(lines)


def do_replacement(rx: re.Pattern[str], text: str, replacement: str) -> tuple[str, int]:
    try:
        return rx.subn(replacement, text)
    except re.error as exc:
        position = f" at position {exc.pos}" if exc.pos is not None else ""
        raise RegexError(f"invalid replacement: {exc.msg}{position}") from exc


def demo() -> int:
    """Exercise groups, replacements, invalid patterns, and empty results."""
    text = SAMPLE_TEXT
    print("Regex Query Tool demo\n" + "=" * 22)
    print("Source text:")
    for line in text.splitlines():
        print(f"  {line}")

    pattern = r"(?P<level>INFO|WARN|ERROR)\s+user=(?P<user>\w+)\s+email=(?P<email>[\w.-]+@[\w.-]+)"
    rx = compile_pattern(pattern)
    records = collect_matches(rx, text)
    print("\n--- named groups ---")
    print(render_matches(pattern, rx, records, len(text)))
    if len(records) != 4 or records[0].named_groups["user"] != "ada":
        print("demo assertion failed: named group extraction", file=sys.stderr)
        return 1

    time_pattern = r"\b\d{2}:\d{2}:\d{2}\b"
    time_rx = compile_pattern(time_pattern)
    time_records = collect_matches(time_rx, text)
    print("\n--- timestamps only ---")
    print(render_matches(time_pattern, time_rx, time_records, len(text)))
    if len(time_records) != 4:
        print("demo assertion failed: timestamp count", file=sys.stderr)
        return 1

    email_pattern = r"(?P<user>[\w.+-]+)@(?P<domain>[\w.-]+)"
    email_rx = compile_pattern(email_pattern, ignore_case=True)
    replaced, count = do_replacement(email_rx, text, r"\g<user> [at] \g<domain>")
    print("\n--- replacement (mask @ with ' [at] ') ---")
    print(f"Substitutions: {count}")
    print(replaced, end="")
    if count != 4 or "@example.com" in replaced:
        print("demo assertion failed: replacement did not mask every address", file=sys.stderr)
        return 1

    print("\n--- invalid pattern ---")
    try:
        compile_pattern(r"([A-Z")
    except RegexError as exc:
        print(f"caught invalid pattern as expected: {exc}")
    else:
        print("demo assertion failed: invalid pattern was accepted", file=sys.stderr)
        return 1

    print("\n--- no matches ---")
    print(render_matches(r"CRITICAL", compile_pattern(r"CRITICAL"), [], len(text)))
    print("\ndemo assertions passed: 4 log lines, 4 timestamps, 4 masked emails")
    return 0


def interactive() -> int:
    """Prompt for text and a pattern; repeat until the user quits."""
    print("Enter source text, then a line containing only '.' to finish:")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line == ".":
            break
        lines.append(line)
    text = "\n".join(lines) + ("\n" if lines else "")
    while True:
        try:
            pattern = input("pattern (blank to quit): ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not pattern:
            return 0
        try:
            rx = compile_pattern(pattern)
            records = collect_matches(rx, text)
            print(render_matches(pattern, rx, records, len(text)))
        except RegexError as exc:
            print(f"error: invalid regular expression: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Match a regular expression against text and show groups and spans.",
        epilog=r"Example: solution.py '\d+' --text 'order 42, item 7' --replace 'N'",
    )
    parser.add_argument("pattern", nargs="?", help="regular expression (omit for interactive mode)")
    parser.add_argument("--text", help="source text; omit to read stdin")
    parser.add_argument("--file", metavar="PATH", help="read source text from a file")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="case-insensitive matching")
    parser.add_argument("-m", "--multiline", action="store_true", help="^ and $ match per line")
    parser.add_argument("-s", "--dotall", action="store_true", help=". matches newlines")
    parser.add_argument("--replace", metavar="TEMPLATE",
                        help=r"replace matches (Python syntax: \1, \g<name>)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--demo", action="store_true", help="run the scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return demo()

    if args.pattern is None:
        if not sys.stdin.isatty():
            parser.print_usage(sys.stderr)
            print("error: a pattern is required (or use --demo)", file=sys.stderr)
            return 2
        return interactive()

    if args.text is not None and args.file:
        print("error: use either --text or --file, not both", file=sys.stderr)
        return 2
    if args.file:
        try:
            text = Path(args.file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
            return 1
    elif args.text is not None:
        text = args.text
    else:
        text = sys.stdin.read()

    try:
        rx = compile_pattern(args.pattern, args.ignore_case, args.multiline, args.dotall)
    except RegexError as exc:
        print(f"error: invalid regular expression: {exc}", file=sys.stderr)
        return 2
    records = collect_matches(rx, text)
    replaced = None
    count = 0
    if args.replace is not None:
        try:
            replaced, count = do_replacement(rx, text, args.replace)
        except RegexError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({
            "pattern": args.pattern,
            "flags": flag_names(rx.flags),
            "match_count": len(records),
            "matches": [record.as_dict() for record in records],
            "replacement": args.replace,
            "substitution_count": count,
            "result": replaced,
        }, indent=2, ensure_ascii=False))
    else:
        print(render_matches(args.pattern, rx, records, len(text)))
        if replaced is not None:
            print(f"\nSubstitutions: {count}\n")
            print(replaced, end="" if replaced.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
