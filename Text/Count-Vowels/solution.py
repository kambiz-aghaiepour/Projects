#!/usr/bin/env python3
"""Count vowels in text and report per-vowel totals and percentages."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

VOWELS = "aeiou"


@dataclass(frozen=True)
class VowelRow:
    """Counts and percentages for one vowel."""

    vowel: str
    count: int
    percent_of_vowels: float
    percent_of_letters: float


@dataclass(frozen=True)
class VowelStats:
    """Aggregate statistics for a piece of text."""

    characters: int
    letters: int
    consonants: int
    vowels: int
    rows: list[VowelRow]


def analyse(text: str, include_y: bool = False) -> VowelStats:
    """Return counts and percentage breakdowns for the supplied text."""
    vowel_set = set(VOWELS + ("y" if include_y else ""))
    lower = text.lower()
    counts = Counter(character for character in lower if character in vowel_set)
    total_vowels = sum(counts.values())
    total_letters = sum(1 for character in text if character.isalpha())
    rows = []
    for vowel in VOWELS + ("y" if include_y else ""):
        count = counts.get(vowel, 0)
        rows.append(
            VowelRow(
                vowel=vowel,
                count=count,
                percent_of_vowels=round(100 * count / total_vowels, 1) if total_vowels else 0.0,
                percent_of_letters=round(100 * count / total_letters, 1) if total_letters else 0.0,
            )
        )
    return VowelStats(
        characters=len(text),
        letters=total_letters,
        consonants=total_letters - total_vowels,
        vowels=total_vowels,
        rows=rows,
    )


def render(text: str, stats: VowelStats) -> str:
    """Format a human-readable report."""
    preview = text if len(text) <= 68 else text[:65] + "..."
    lines = [
        f"Text:       {preview!r}",
        (
            f"Characters: {stats.characters}  |  Letters: {stats.letters}  |  "
            f"Vowels: {stats.vowels}  |  Consonants: {stats.consonants}"
        ),
        "",
        f"{'Vowel':<7}{'Count':>6}{'% of vowels':>15}{'% of letters':>15}",
        "-" * 43,
    ]
    for row in stats.rows:
        lines.append(
            f"{row.vowel:<7}{row.count:>6}{row.percent_of_vowels:>14.1f}%"
            f"{row.percent_of_letters:>14.1f}%"
        )
    lines.append("-" * 43)
    total_vowel_pct = 100.0 if stats.vowels else 0.0
    total_letter_pct = 100.0 * stats.vowels / stats.letters if stats.letters else 0.0
    lines.append(
        f"{'Total':<7}{stats.vowels:>6}{total_vowel_pct:>14.1f}%{total_letter_pct:>14.1f}%"
    )
    return "\n".join(lines)


def read_input(text: str | None, file: str | None, encoding: str) -> str | None:
    """Read text from an argument, a file, stdin, or an interactive prompt."""
    if text is not None:
        return text
    if file:
        try:
            return Path(file).read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"error: cannot read {file}: {exc}", file=sys.stderr)
            return None
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return input("Text: ")


def demo() -> int:
    """Report on a pangram, then show the effect of counting ``y``."""
    sentence = "The quick brown fox jumps over the lazy dog."
    print("Default vowels (a, e, i, o, u):")
    stats = analyse(sentence)
    print(render(sentence, stats))

    y_text = "Myth: rhythm and rhyme rarely fly by."
    print("\nWith --include-y (y counted as a vowel):")
    print(render(y_text, analyse(y_text, include_y=True)))

    excerpt = {"vowels": stats.vowels, "counts": [asdict(row) for row in stats.rows[:2]]}
    print("\nJSON excerpt:")
    print(json.dumps(excerpt, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Count vowels and show per-vowel counts and percentages.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --text 'Hello there'\n"
            "  python3 solution.py --include-y --text 'rhythm'\n"
            "  cat notes.txt | python3 solution.py --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="text to analyse")
    source.add_argument("--file", metavar="PATH", help="read text from a UTF-8 file")
    parser.add_argument("--include-y", action="store_true", help="count y as a vowel")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--encoding", default="utf-8", help="file encoding (default: utf-8)")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return demo()

    text = read_input(args.text, args.file, args.encoding)
    if text is None:
        return 1
    stats = analyse(text, args.include_y)
    if args.json:
        print(json.dumps(asdict(stats), indent=2))
    else:
        print(render(text, stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
