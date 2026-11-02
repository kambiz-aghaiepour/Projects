#!/usr/bin/env python3
"""Check whether text is a palindrome, optionally normalising it first.

By default the check ignores letter case, punctuation, whitespace, and
accents, so phrases such as "A man, a plan, a canal: Panama" pass.  Use
--exact to compare the raw text or --case-sensitive to keep case while still
ignoring punctuation and spacing.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one palindrome check."""

    original: str
    normalized: str
    is_palindrome: bool
    first_mismatch: tuple[int, str, str] | None


def normalise(text: str, case_sensitive: bool = False, fold_accents: bool = True) -> str:
    """Reduce text to the characters that participate in the comparison."""
    if fold_accents:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(character for character in text if not unicodedata.combining(character))
    if not case_sensitive:
        text = text.casefold()
    return "".join(character for character in text if character.isalnum())


def check(
    text: str,
    exact: bool = False,
    case_sensitive: bool = False,
    fold_accents: bool = True,
) -> CheckResult:
    """Compare the text with its reverse, recording the first mismatch."""
    if exact:
        normalized = text
    else:
        normalized = normalise(text, case_sensitive=case_sensitive, fold_accents=fold_accents)

    reversed_text = normalized[::-1]
    if normalized == reversed_text:
        return CheckResult(text, normalized, True, None)

    limit = (len(normalized) + 1) // 2
    for index in range(limit):
        left = normalized[index]
        right = reversed_text[index]
        if left != right:
            return CheckResult(text, normalized, False, (index, left, right))
    return CheckResult(text, normalized, False, None)


def describe(result: CheckResult, show_normalized: bool = True) -> str:
    """Render a readable verdict for one check."""
    verdict = "YES — palindrome" if result.is_palindrome else "NO — not a palindrome"
    lines = [f"Input:  {result.original!r}", f"Result: {verdict}"]
    if show_normalized:
        normalized = result.normalized
        if len(normalized) > 78:
            normalized = normalized[:75] + "..."
        lines.append(f"Normalized: {normalized!r} ({len(result.normalized)} characters)")
    if result.first_mismatch is not None:
        position, left, right = result.first_mismatch
        lines.append(f"First mismatch at position {position}: {left!r} vs {right!r}")
    return "\n".join(lines)


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
    return input("Text to check: ")


def demo() -> int:
    """Check a mix of words, phrases, accented text, and a negative case."""
    samples = [
        "racecar",
        "A man, a plan, a canal: Panama",
        "No 'x' in Nixon",
        "La mariée ira mal",
        "Hello, world!",
    ]
    print("Palindrome checks (case, punctuation, whitespace, accents ignored):\n")
    for sample in samples:
        result = check(sample)
        print(describe(result))
        print()

    strict = check("Racecar", exact=True)
    print("With --exact (raw comparison):")
    print(describe(strict))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check if text reads the same forwards and backwards.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --text 'A man, a plan, a canal: Panama'\n"
            "  python3 solution.py --text 'Racecar' --exact\n"
            "  cat phrase.txt | python3 solution.py --case-sensitive"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="text to check")
    source.add_argument("--file", metavar="PATH", help="read text from a UTF-8 file")
    parser.add_argument(
        "--exact", action="store_true", help="compare raw characters instead of normalising"
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="keep case (punctuation and whitespace are still ignored)",
    )
    parser.add_argument(
        "--keep-accents", action="store_true", help="do not strip combining accents"
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
    result = check(
        text,
        exact=args.exact,
        case_sensitive=args.case_sensitive,
        fold_accents=not args.keep_accents,
    )
    print(describe(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
