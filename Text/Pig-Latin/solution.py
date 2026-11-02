#!/usr/bin/env python3
"""Translate English text into Pig Latin, preserving punctuation and case.

Rules implemented:

* vowel-initial words take ``-way``  ("apple" -> "appleway")
* consonant clusters move to the end with ``-ay``  ("string" -> "ingstray")
* ``qu`` counts as a consonant unit  ("quick" -> "ickquay")
* ``y`` is a consonant at the start of a syllable and a vowel after a
  consonant  ("yellow" -> "ellowyay", "rhythm" -> "ythmrhay")
* words without a vowel simply take ``-ay``  ("nth" -> "nthay")
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

VOWELS = frozenset("aeiou")
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*")


def first_vowel_index(word: str) -> int:
    """Return the index where the initial consonant cluster ends.

    ``qu`` is skipped as a unit, and ``y`` only counts as a vowel when it
    follows a consonant (so it can end a cluster but not start a word).
    """
    lower = word.lower()
    index = 0
    while index < len(lower):
        character = lower[index]
        if character in VOWELS:
            return index
        if character == "q" and lower[index + 1 : index + 2] == "u":
            index += 2
            continue
        if character == "y" and index > 0 and lower[index - 1] not in VOWELS:
            return index
        index += 1
    return -1


def pig_latin_word(word: str) -> str:
    """Translate a single alphabetic word, preserving its capitalisation."""
    lower = word.lower()
    if not lower:
        return word

    if lower[0] in VOWELS:
        translated = lower + "way"
    else:
        split = first_vowel_index(lower)
        if split == -1:
            translated = lower + "ay"
        elif split == 0:
            translated = lower + "way"
        else:
            translated = lower[split:] + lower[:split] + "ay"

    if word.isupper() and len(word) > 1:
        return translated.upper()
    if word[0].isupper():
        return translated[0].upper() + translated[1:]
    return translated


def translate(text: str) -> str:
    """Translate all words in ``text``, leaving punctuation and spacing alone."""
    return WORD_PATTERN.sub(lambda match: pig_latin_word(match.group(0)), text)


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
    return input("English text: ")


def demo() -> int:
    """Show the rule set with individual words and a full sentence."""
    words = [
        "banana",
        "apple",
        "string",
        "school",
        "quick",
        "yellow",
        "rhythm",
        "nth",
        "Hello",
        "HELLO",
        "don't",
    ]
    print("Word translations:")
    width = max(len(word) for word in words)
    for word in words:
        print(f"  {word:<{width}} -> {pig_latin_word(word)}")

    sentence = "Hello, world! The quick brown fox doesn't jump over 3 lazy dogs."
    print(f"\nSentence:\n  {sentence}")
    print(f"  {translate(sentence)}")

    hyphenated = "Well-known state-of-the-art tools."
    print(f"\nHyphenated text:\n  {hyphenated}")
    print(f"  {translate(hyphenated)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translate English text to Pig Latin, preserving punctuation.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --text 'banana split'\n"
            "  echo 'Hello, world!' | python3 solution.py\n"
            "  python3 solution.py --file notes.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="text to translate")
    source.add_argument("--file", metavar="PATH", help="read text from a UTF-8 file")
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
    print(translate(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
