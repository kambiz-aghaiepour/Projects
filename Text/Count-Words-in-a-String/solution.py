#!/usr/bin/env python3
"""Count words in text or files and summarise lines, uniqueness, and frequency.

Input can come from ``--text``, one or more files (``-`` means stdin), piped
stdin, or an interactive prompt.  Multiple files are reported individually and
as a combined summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

WORD_RE = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class TextStats:
    """Word statistics for one source of text."""

    label: str
    characters: int
    lines: int
    words: int
    unique: int
    average_word_length: float
    longest_word: str
    top: list[tuple[str, int]]
    frequencies: Counter[str] = field(default_factory=Counter, repr=False, compare=False)
    total_word_length: int = field(default=0, repr=False, compare=False)


def count_lines(text: str) -> int:
    """Count physical lines, including a final line without a newline."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def extract_words(text: str) -> list[str]:
    """Return word tokens, keeping internal apostrophes."""
    return WORD_RE.findall(text)


def analyse(label: str, text: str, top_n: int = 5, case_sensitive: bool = False) -> TextStats:
    """Compute the statistics used by the report."""
    words = extract_words(text)
    keys = words if case_sensitive else [word.casefold() for word in words]
    frequencies = Counter(keys)
    longest = max(words, key=len) if words else ""
    total_word_length = sum(len(word) for word in words)
    return TextStats(
        label=label,
        characters=len(text),
        lines=count_lines(text),
        words=len(words),
        unique=len(frequencies),
        average_word_length=round(total_word_length / len(words), 1) if words else 0.0,
        longest_word=longest,
        top=frequencies.most_common(top_n),
        frequencies=frequencies,
        total_word_length=total_word_length,
    )


def combine(label: str, stats: Sequence[TextStats], top_n: int) -> TextStats:
    """Merge per-source statistics into one summary."""
    frequencies: Counter[str] = Counter()
    for item in stats:
        frequencies.update(item.frequencies)
    total_words = sum(item.words for item in stats)
    total_word_length = sum(item.total_word_length for item in stats)
    return TextStats(
        label=label,
        characters=sum(item.characters for item in stats),
        lines=sum(item.lines for item in stats),
        words=total_words,
        unique=len(frequencies),
        average_word_length=round(total_word_length / total_words, 1) if total_words else 0.0,
        longest_word=max((item.longest_word for item in stats), key=len, default=""),
        top=frequencies.most_common(top_n),
        frequencies=frequencies,
        total_word_length=total_word_length,
    )


def render(stats: TextStats) -> str:
    """Format one source's statistics."""
    lines = [
        f"Source: {stats.label}",
        (
            f"Characters: {stats.characters}  |  Lines: {stats.lines}  |  "
            f"Words: {stats.words}  |  Unique words: {stats.unique}"
        ),
        f"Average word length: {stats.average_word_length}  |  Longest word: {stats.longest_word!r}",
    ]
    if stats.top:
        lines.append("")
        lines.append(f"Top {len(stats.top)} word(s):")
        for rank, (word, count) in enumerate(stats.top, start=1):
            percent = 100 * count / stats.words if stats.words else 0.0
            lines.append(f"  {rank:>2}. {word:<18} {count:>4}  ({percent:4.1f}%)")
    return "\n".join(lines)


def render_table(stats: Sequence[TextStats]) -> str:
    """Format a compact per-file table."""
    lines = [f"{'File':<24}{'Lines':>7}{'Words':>7}{'Unique':>8}"]
    lines.append("-" * 46)
    for item in stats:
        lines.append(
            f"{item.label[:23]:<24}{item.lines:>7}{item.words:>7}{item.unique:>8}"
        )
    return "\n".join(lines)


def stats_dict(stats: TextStats) -> dict[str, object]:
    """Convert statistics to JSON-friendly data, recomputing percentages."""
    data = asdict(stats)
    data.pop("frequencies", None)
    data.pop("total_word_length", None)
    data["top"] = [
        {
            "word": word,
            "count": count,
            "percent": round(100 * count / stats.words, 2) if stats.words else 0.0,
        }
        for word, count in stats.top
    ]
    return data


def read_file(path: str, encoding: str) -> str | None:
    """Read one input path; ``-`` means standard input."""
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return None


def demo() -> int:
    """Summarise an inline string and two temporary files."""
    sample = "The quick brown fox jumps over the lazy dog. The dog sleeps; the fox runs."
    print("String input:")
    print(render(analyse("<text>", sample, top_n=5)))
    print()

    with tempfile.TemporaryDirectory() as directory:
        files = {
            "poem.txt": (
                "The quick brown fox jumps over the lazy dog.\n"
                "The dog sleeps; the fox runs.\n"
            ),
            "notes.txt": (
                "Quick foxes are clever.\n"
                "The lazy dog dreams of quick foxes.\n"
            ),
        }
        paths = []
        for name, content in files.items():
            path = Path(directory) / name
            path.write_text(content, encoding="utf-8")
            paths.append(path)

        per_file = [analyse(path.name, path.read_text(encoding="utf-8"), top_n=5) for path in paths]
        print("Multiple files:")
        print(render_table(per_file))
        print()
        print("Combined summary:")
        print(render(combine("all sources", per_file, top_n=5)))

    print("\nJSON excerpt:")
    print(json.dumps(stats_dict(analyse("<text>", sample, top_n=3)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Count words and summarise one or more text sources.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --text 'one two two three'\n"
            "  python3 solution.py poem.txt notes.txt\n"
            "  cat notes.txt | python3 solution.py --top 10\n"
            "  python3 solution.py - --json < notes.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="*", metavar="FILE", help="files to read; '-' means stdin")
    parser.add_argument("--text", help="analyse a literal string instead of files")
    parser.add_argument("--top", type=int, default=5, metavar="N", help="show N top words (default 5)")
    parser.add_argument(
        "--case-sensitive", action="store_true", help="treat 'The' and 'the' as different words"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--encoding", default="utf-8", help="file encoding (default: utf-8)")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return demo()
    if args.top < 1:
        parser.error("--top must be at least 1")
    if args.text is not None and args.files:
        parser.error("use either --text or FILE arguments, not both")

    sources: list[TextStats] = []
    if args.text is not None:
        sources.append(analyse("<text>", args.text, args.top, args.case_sensitive))
    elif args.files:
        for path in args.files:
            content = read_file(path, args.encoding)
            if content is None:
                return 1
            label = "<stdin>" if path == "-" else Path(path).name
            sources.append(analyse(label, content, args.top, args.case_sensitive))
    elif not sys.stdin.isatty():
        sources.append(analyse("<stdin>", sys.stdin.read(), args.top, args.case_sensitive))
    else:
        print("Enter text, then press Ctrl-D (Ctrl-Z on Windows) to finish:", file=sys.stderr)
        sources.append(analyse("<stdin>", sys.stdin.read(), args.top, args.case_sensitive))

    summary = combine("all sources", sources, args.top)

    if args.json:
        payload: dict[str, object] = {
            "sources": [stats_dict(item) for item in sources],
            "summary": stats_dict(summary),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if len(sources) > 1:
        print(render_table(sources))
        print()
        print(render(summary))
    else:
        print(render(sources[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
