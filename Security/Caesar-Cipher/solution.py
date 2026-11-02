#!/usr/bin/env python3
"""Caesar cipher: encode, decode, brute force, and frequency analysis.

The cipher shifts each ASCII letter by a key from 1 to 25, wrapping Z to A
and preserving case; every non-letter character is left untouched.  The
module also provides brute-force enumeration of all 25 keys and a simple
English frequency analysis to help break ciphertext.
"""

from __future__ import annotations

import argparse
import re
import string
import sys
from collections import Counter

ALPHABET = string.ascii_lowercase

# Relative frequencies of letters in English text, in percent.
ENGLISH_FREQ: dict[str, float] = {
    "a": 8.167, "b": 1.492, "c": 2.782, "d": 4.253, "e": 12.702,
    "f": 2.228, "g": 2.015, "h": 6.094, "i": 6.966, "j": 0.153,
    "k": 0.772, "l": 4.025, "m": 2.406, "n": 6.749, "o": 7.507,
    "p": 1.929, "q": 0.095, "r": 5.987, "s": 6.327, "t": 9.056,
    "u": 2.758, "v": 0.978, "w": 2.360, "x": 0.150, "y": 1.974,
    "z": 0.074,
}

# Frequent English words used to break ties between similar chi-squared scores.
COMMON_WORDS = frozenset(
    """the and that have for not with you this but his from they say her she will
    one all would there their what so up out if about who get which go me when make
    can like time no just him know take people into year your good some could them
    see other than then now look only come its over think also back after use two
    how our work first well way even new want because any these give day most us""".split()
)


def validate_key(key: int) -> None:
    """Raise ValueError unless key is a valid Caesar key (1-25)."""
    if not 1 <= key <= 25:
        raise ValueError(f"key must be an integer from 1 to 25, got {key}")


def shift_text(text: str, key: int) -> str:
    """Shift every ASCII letter by ``key`` positions, wrapping around.

    Case is preserved and all non-letters are copied unchanged.  ``key`` may
    be any integer; it is reduced modulo 26.
    """
    shift = key % 26
    if shift == 0:
        return text
    out: list[str] = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:
            out.append(chr(65 + (code - 65 + shift) % 26))
        elif 97 <= code <= 122:
            out.append(chr(97 + (code - 97 + shift) % 26))
        else:
            out.append(char)
    return "".join(out)


def encode(text: str, key: int) -> str:
    """Encrypt text with a Caesar key."""
    validate_key(key)
    return shift_text(text, key)


def decode(text: str, key: int) -> str:
    """Decrypt text encrypted with a Caesar key."""
    validate_key(key)
    return shift_text(text, -key)


def all_shifts(text: str) -> list[tuple[int, str]]:
    """Return every (key, decrypted text) pair for keys 1 through 25."""
    return [(key, shift_text(text, -key)) for key in range(1, 26)]


def letter_counts(text: str) -> Counter[str]:
    """Count ASCII letters case-insensitively."""
    return Counter(char.lower() for char in text if char.lower() in ALPHABET)


def chi_squared(text: str) -> float:
    """Chi-squared distance from English letter frequencies (lower is closer)."""
    counts = letter_counts(text)
    total = sum(counts.values())
    if total == 0:
        return float("inf")
    score = 0.0
    for letter, percent in ENGLISH_FREQ.items():
        expected = total * percent / 100.0
        observed = counts.get(letter, 0)
        score += (observed - expected) ** 2 / expected
    return score


def common_word_hits(text: str) -> int:
    """Count occurrences of frequent English words (helps on short texts)."""
    words = re.findall(r"[a-z]+", text.lower())
    return sum(1 for word in words if word in COMMON_WORDS)


def plausibility(text: str) -> float:
    """Heuristic score for how much ``text`` looks like English (lower is better)."""
    return chi_squared(text) - 3.0 * common_word_hits(text)


def rank_shifts(text: str) -> list[tuple[int, str, float]]:
    """Rank all 25 candidate decodings by plausibility, best first."""
    rows = [
        (key, candidate, plausibility(candidate))
        for key, candidate in all_shifts(text)
    ]
    rows.sort(key=lambda row: (row[2], row[0]))
    return rows


def preview(text: str, width: int = 60) -> str:
    """Collapse whitespace and shorten text for one-line display."""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[:width].rstrip() + "..."


def frequency_report(text: str) -> str:
    """Explain the letter frequencies and likely Caesar keys for ``text``."""
    counts = letter_counts(text)
    total = sum(counts.values())
    if total == 0:
        return "No letters to analyse."
    lines = [f"Letters analysed: {total}", "Most common letters:"]
    for letter, count in counts.most_common(8):
        lines.append(f"  {letter}  {count:4d}  {100 * count / total:5.1f}%")
    lines.append("English reference order: e t a o i n s h r d l u")
    common_letter = counts.most_common(1)[0][0]
    guessed_key = (ALPHABET.index(common_letter) - ALPHABET.index("e")) % 26
    lines.append(
        f"Most common letter '{common_letter}' implies key {guessed_key} "
        "if it stands for 'e'"
    )
    lines.append("Best keys by chi-squared fit (lower is better):")
    for key, plaintext, score in rank_shifts(text)[:3]:
        lines.append(f"  key {key:2d}  score {score:8.2f}  {preview(plaintext)}")
    return "\n".join(lines)


def print_brute(text: str) -> None:
    """Print the text decoded under every key, marking the best guess."""
    has_letters = bool(letter_counts(text))
    best_key = rank_shifts(text)[0][0] if has_letters else None
    print(f"All 25 keys for: {preview(text)}")
    for key, candidate in all_shifts(text):
        marker = "  <-- best guess" if key == best_key else ""
        print(f"  {key:2d}: {candidate}{marker}")


def resolve_text(value: str | None) -> str:
    """Use the given text, stdin when piped, or prompt on a terminal."""
    if value is not None and value != "-":
        return value
    if sys.stdin.isatty():
        return input("Text: ")
    text = sys.stdin.read().rstrip("\n")
    if not text:
        raise ValueError("no input text provided")
    return text


def prompt_key() -> int | None:
    """Ask for a key until valid; return None if the user cancels."""
    while True:
        try:
            raw = input("Key (1-25): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            return None
        try:
            key = int(raw)
            validate_key(key)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        return key


def interactive() -> int:
    """Small menu-driven interface for all four operations."""
    print("Caesar Cipher - interactive mode")
    while True:
        print(
            "\n1) Encode\n2) Decode\n3) Brute force all keys\n"
            "4) Frequency analysis\n5) Quit"
        )
        try:
            choice = input("Choice [1-5]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in {"5", "q", "quit", "exit"}:
            return 0
        if choice not in {"1", "2", "3", "4"}:
            print("Please enter 1, 2, 3, 4, or 5.")
            continue
        try:
            text = input("Text: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            print("No text given.")
            continue
        if choice in {"1", "2"}:
            key = prompt_key()
            if key is None:
                print("Cancelled.")
                continue
            result = encode(text, key) if choice == "1" else decode(text, key)
            print(f"Result: {result}")
        elif choice == "3":
            print_brute(text)
        else:
            print(frequency_report(text))


def run_demo() -> int:
    """Scripted demonstration of every feature; never reads input."""
    print("Caesar Cipher demo")
    print("=" * 62)
    print("Known examples from the problem statement:")
    print(f"  encode('HI',  2) = {encode('HI', 2)!r}")
    print(f"  decode('JK',  2) = {decode('JK', 2)!r}")
    print(f"  encode('HI', 20) = {encode('HI', 20)!r}")
    print()

    message = "Attack at Dawn, 06:30!"
    print(f"Round trips for {message!r}:")
    for key in (3, 13, 25):
        encrypted = encode(message, key)
        decrypted = decode(encrypted, key)
        print(f"  key {key:2d}: {encrypted}")
        print(f"          back: {decrypted}  (match: {decrypted == message})")
    print()

    secret = encode("The quick brown fox jumps over the lazy dog", 3)
    print(f"Brute force of {secret!r} (encrypted with key 3):")
    print_brute(secret)
    print()

    passage = (
        "It was the best of times, it was the worst of times, it was the age "
        "of wisdom, it was the age of foolishness, it was the epoch of belief, "
        "it was the epoch of incredulity, it was the season of light, it was "
        "the season of darkness, it was the spring of hope, it was the winter "
        "of despair, we had everything before us, we had nothing before us."
    )
    ciphertext = encode(passage, 7)
    print("Frequency analysis of a longer ciphertext (true key 7):")
    print(f"  ciphertext: {preview(ciphertext)}")
    print(frequency_report(ciphertext))
    best_key = rank_shifts(ciphertext)[0][0]
    print(f"  best key detected: {best_key} (expected 7)")
    print()
    print("Demo complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Encode, decode, brute force, and analyse Caesar ciphers.",
        epilog=(
            "Examples:\n"
            "  python3 solution.py --demo\n"
            "  python3 solution.py encode 'Hello, World!' -k 3\n"
            "  python3 solution.py decode 'Khoor, Zruog!' -k 3\n"
            "  python3 solution.py brute 'KHOOR ZRUOG'\n"
            "  python3 solution.py analyze 'Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj'\n"
            "Run with no command for the interactive menu."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demonstration")
    sub = parser.add_subparsers(dest="command", metavar="command")

    for name, help_text in (
        ("encode", "encrypt text with a key"),
        ("decode", "decrypt text with a key"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("text", nargs="?", help="text to process (omit or '-' for stdin)")
        command.add_argument("-k", "--key", type=int, required=True, help="key from 1 to 25")

    brute = sub.add_parser("brute", help="try all 25 keys and mark the best guess")
    brute.add_argument("text", nargs="?", help="ciphertext (omit or '-' for stdin)")

    analyze = sub.add_parser("analyze", help="letter frequency and likely-key report")
    analyze.add_argument("text", nargs="?", help="ciphertext (omit or '-' for stdin)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to a command, demo, or interactive menu."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if args.command is None:
        try:
            return interactive()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
    try:
        text = resolve_text(args.text)
        if args.command == "encode":
            print(encode(text, args.key))
        elif args.command == "decode":
            print(decode(text, args.key))
        elif args.command == "brute":
            print_brute(text)
        else:
            print(frequency_report(text))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
