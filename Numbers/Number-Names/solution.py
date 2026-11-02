#!/usr/bin/env python3
"""Spell out numbers in English.

Supports zero, negative integers, decimals and values up to 10^36 - 1
(decillions).  Decimal digits are read individually after "point", so
``3.140`` becomes "three point one four zero".

Examples:
    python3 solution.py 1234567
    python3 solution.py -42 3.14
    python3 solution.py 101 --and
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation

ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
        "eighty", "ninety")
SCALES = (
    "", "thousand", "million", "billion", "trillion", "quadrillion",
    "quintillion", "sextillion", "septillion", "octillion", "nonillion",
    "decillion",
)
MAX_VALUE = 1000 ** len(SCALES)


def _two_digits(n: int) -> str:
    """Spell a number from 0 to 99."""

    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f"-{ONES[ones]}" if ones else "")


def _three_digits(n: int, use_and: bool) -> str:
    """Spell a number from 0 to 999."""

    hundreds, remainder = divmod(n, 100)
    parts: list[str] = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} hundred")
    if remainder:
        if hundreds and use_and:
            parts.append("and")
        parts.append(_two_digits(remainder))
    return " ".join(parts)


def integer_to_words(n: int, use_and: bool = False) -> str:
    """Spell an integer (positive, negative or zero)."""

    if n == 0:
        return "zero"
    negative = n < 0
    n = abs(n)
    if n >= MAX_VALUE:
        raise ValueError(f"number is too large; maximum is {MAX_VALUE - 1:,}")

    lowest_chunk = n % 1000
    groups: list[str] = []
    scale_index = 0
    while n:
        chunk = n % 1000
        if chunk:
            words = _three_digits(chunk, use_and)
            scale = SCALES[scale_index]
            groups.append(f"{words} {scale}".strip())
        n //= 1000
        scale_index += 1

    ordered = list(reversed(groups))
    if use_and and len(ordered) > 1 and 0 < lowest_chunk < 100:
        ordered[-1] = f"and {ordered[-1]}"
    text = ", ".join(ordered)
    if use_and:
        text = text.replace(", and ", " and ")
    return f"minus {text}" if negative else text


def number_to_words(text: str, use_and: bool = False) -> str:
    """Spell an integer or decimal written as a string."""

    cleaned = text.strip().replace(",", "").replace("_", "")
    if not cleaned:
        raise ValueError("empty number")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid number {text!r}") from exc
    if not value.is_finite():
        raise ValueError("number must be finite")

    negative = value < 0
    fixed = format(abs(value), "f")
    whole_text, _, fraction = fixed.partition(".")
    whole = int(whole_text)
    if whole >= MAX_VALUE:
        raise ValueError(f"number is too large; maximum is {MAX_VALUE - 1:,}")

    words = integer_to_words(-whole if negative else whole, use_and)
    if fraction and any(digit != "0" for digit in fraction):
        digits = " ".join(ONES[int(digit)] for digit in fraction)
        words = f"{words} point {digits}"
    return words


def run_demo() -> int:
    """Print a selection of integer, negative and decimal readings."""

    print("Number Names demo")
    print("=" * 58)
    examples = ["0", "7", "21", "100", "101", "999", "1000", "12345",
                "1000000", "-42", "3.14", "1234567890123"]
    for text in examples:
        print(f"  {text:>16} -> {number_to_words(text)}")

    print("\nBritish 'and' style:")
    for text in ("101", "1001", "1234567"):
        print(f"  {text:>16} -> {number_to_words(text, use_and=True)}")

    print("\nDecimals keep every written digit:")
    for text in ("0.05", "3.140", "2.5", "1000000.001"):
        print(f"  {text:>16} -> {number_to_words(text)}")

    print(f"\nSupported range: |n| < {MAX_VALUE:,} (up to decillions).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spell numbers out in English (integers and decimals).",
        epilog="Examples: solution.py 1234567 | solution.py -3.14 | solution.py 101 --and",
    )
    parser.add_argument("numbers", nargs="*", help="numbers to spell out")
    parser.add_argument("--and", dest="use_and", action="store_true",
                        help="include 'and' after hundreds (British style)")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.numbers:
        failed = False
        for text in args.numbers:
            try:
                print(f"{text}: {number_to_words(text, args.use_and)}")
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                failed = True
        return 1 if failed else 0

    print("Enter numbers to spell out (blank line to quit).")
    while True:
        try:
            line = input("number> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line.strip():
            return 0
        try:
            print(number_to_words(line, args.use_and))
        except ValueError as exc:
            print(f"error: {exc}")


if __name__ == "__main__":
    sys.exit(main())
