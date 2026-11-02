#!/usr/bin/env python3
"""Reverse a string by code points, grapheme clusters, words, or lines.

Character reversal is the classic exercise.  ``--graphemes`` reverses visual
characters instead so accented letters and emoji sequences stay intact, while
``--mode words`` turns "the quick brown fox" into "fox brown quick the".
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Sequence

MODES = ("chars", "words", "lines")
REGIONAL_INDICATORS = range(0x1F1E6, 0x1F200)
EMOJI_MODIFIERS = range(0x1F3FB, 0x1F400)
VARIATION_SELECTORS = set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))


def reverse_characters(text: str) -> str:
    """Reverse the string by Unicode code point."""
    return text[::-1]


def _is_extender(character: str) -> bool:
    """Return True for marks that attach to the preceding character."""
    code = ord(character)
    return (
        unicodedata.combining(character) != 0
        or unicodedata.category(character) in {"Mn", "Me", "Mc"}
        or code in VARIATION_SELECTORS
        or code in EMOJI_MODIFIERS
        or code == 0x20E3  # combining enclosing keycap
    )


def _ends_with_joiner(cluster: str) -> bool:
    return cluster.endswith("\u200d")


def grapheme_clusters(text: str) -> list[str]:
    """Split text into approximate grapheme clusters (UAX #29 subset).

    Handles combining marks, emoji variation selectors and skin-tone
    modifiers, zero-width-joiner sequences, keycaps, and flags made from
    pairs of regional-indicator letters.
    """
    clusters: list[str] = []
    for character in text:
        if not clusters:
            clusters.append(character)
            continue
        previous = clusters[-1]
        if _ends_with_joiner(previous) or character == "\u200d":
            clusters[-1] += character
        elif previous[-1] == "\r" and character == "\n":
            clusters[-1] += character
        elif _is_extender(character):
            clusters[-1] += character
        elif ord(character) in REGIONAL_INDICATORS:
            # Pair flags: only join if the previous cluster is a lone symbol.
            if len(previous) == 1 and ord(previous) in REGIONAL_INDICATORS:
                clusters[-1] += character
            else:
                clusters.append(character)
        else:
            clusters.append(character)
    return clusters


def reverse_graphemes(text: str) -> str:
    """Reverse the string while keeping grapheme clusters intact."""
    return "".join(reversed(grapheme_clusters(text)))


def reverse_words(text: str) -> str:
    """Reverse word order, normalising runs of whitespace to one space."""
    return " ".join(reversed(text.split()))


def reverse_lines(text: str) -> str:
    """Reverse line order, preserving each line's content."""
    return "\n".join(reversed(text.splitlines()))


def reverse(text: str, mode: str, by_graphemes: bool = False) -> str:
    """Dispatch to the requested reversal strategy."""
    if mode == "words":
        return reverse_words(text)
    if mode == "lines":
        return reverse_lines(text)
    return reverse_graphemes(text) if by_graphemes else reverse_characters(text)


def read_input(text: str | None, file: str | None, encoding: str) -> str | None:
    """Read text from an argument, a file, stdin, or an interactive prompt."""
    if text is not None:
        return text
    if file:
        try:
            content = Path(file).read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"error: cannot read {file}: {exc}", file=sys.stderr)
            return None
        return content[:-1] if content.endswith("\n") else content
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return input("Text to reverse: ")


def demo() -> int:
    """Run scripted examples for every mode and both character algorithms."""
    samples = [
        ("Hello, world!", "chars", False),
        ("the quick brown fox", "words", False),
        ("first line\nsecond line\nthird line", "lines", False),
        ("café", "chars", False),
    ]
    print("Reversal examples:")
    for text, mode, by_graphemes in samples:
        label = mode if not by_graphemes else "graphemes"
        shown = repr(text)
        result = repr(reverse(text, mode, by_graphemes))
        print(f"  {label:<9} {shown:<44} -> {result}")

    decomposed = "e\u0301"  # e + combining acute accent, one visual character
    print("\nCode points vs grapheme clusters (decomposed 'e' + accent):")
    print(f"  code points: {ascii(reverse_characters(decomposed))}")
    print(f"  graphemes:   {ascii(reverse_graphemes(decomposed))}")

    family = "\U0001f469\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466"
    print("\nEmoji sequence (family) reversed with --graphemes:")
    print(f"  {reverse_graphemes(family + '!')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reverse characters, grapheme clusters, words, or lines.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --text 'Hello, world!'\n"
            "  python3 solution.py --text 'the quick brown fox' --mode words\n"
            "  printf 'a\\nb\\nc\\n' | python3 solution.py --mode lines"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="string to reverse")
    source.add_argument("--file", metavar="PATH", help="read text from a UTF-8 file")
    parser.add_argument(
        "--mode", choices=MODES, default="chars", help="what to reverse (default: chars)"
    )
    parser.add_argument(
        "--graphemes",
        action="store_true",
        help="in chars mode, keep combining marks and emoji sequences together",
    )
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
    result = reverse(text, args.mode, args.graphemes)
    if result.endswith("\n"):
        sys.stdout.write(result)
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
