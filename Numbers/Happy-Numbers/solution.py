#!/usr/bin/env python3
"""Find and inspect happy numbers.

A happy number reaches 1 when you repeatedly replace it by the sum of the
squares of its digits.  Unhappy numbers eventually enter a cycle that does
not contain 1 (4 -> 16 -> 37 -> ...).

Examples:
    python3 solution.py --count 8
    python3 solution.py --check 19 --path
    python3 solution.py --check 4
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import sys


def digit_square_sum(n: int) -> int:
    """Return the sum of the squares of the decimal digits of ``n``."""

    if n < 0:
        raise ValueError("happy numbers are defined for non-negative integers")
    total = 0
    while n:
        n, digit = divmod(n, 10)
        total += digit * digit
    return total


def happy_path(n: int, limit: int = 1000) -> tuple[bool, list[int]]:
    """Return ``(is_happy, sequence)`` for ``n`` using cycle detection."""

    if n < 1:
        raise ValueError("happy numbers start at 1")
    seen: set[int] = set()
    sequence = [n]
    current = n
    while current != 1 and current not in seen and len(sequence) <= limit:
        seen.add(current)
        current = digit_square_sum(current)
        sequence.append(current)
    return current == 1, sequence


def is_happy(n: int) -> bool:
    """Return True when ``n`` is a happy number."""

    return happy_path(n)[0]


def find_happy(count: int, start: int = 1, limit: int = 1_000_000) -> list[int]:
    """Return the first ``count`` happy numbers at or after ``start``."""

    if count < 0:
        raise ValueError("count must be non-negative")
    found: list[int] = []
    candidate = max(1, start)
    while len(found) < count and candidate <= limit:
        if is_happy(candidate):
            found.append(candidate)
        candidate += 1
    if len(found) < count:
        raise ValueError(f"found only {len(found)} happy numbers up to {limit}")
    return found


def run_demo() -> int:
    """Print the first eight happy numbers and walk two example paths."""

    print("Happy Numbers demo")
    print("=" * 56)
    first_eight = find_happy(8)
    print("First 8 happy numbers:")
    print(f"  {', '.join(str(number) for number in first_eight)}")

    print("\nWhy 19 is happy:")
    happy, path = happy_path(19)
    print(f"  {' -> '.join(str(number) for number in path)}  ({'happy' if happy else 'unhappy'})")

    print("\nWhy 4 is unhappy:")
    happy, path = happy_path(4)
    cycle = path[path.index(path[-1]):] if path[-1] in path[:-1] else path
    print(f"  {' -> '.join(str(number) for number in path)}  ({'happy' if happy else 'unhappy'})")
    print(f"  detected cycle length: {len(cycle) - 1 if len(cycle) > 1 else 'n/a'}")

    print("\nDensity check:")
    for upper in (100, 1_000, 10_000):
        count = sum(1 for n in range(1, upper + 1) if is_happy(n))
        print(f"  {count:>4} happy numbers in 1..{upper:,} ({count / upper:.1%})")

    print(f"\nFirst 20 happy numbers: {find_happy(20)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find happy numbers and show their digit-square sequences.",
    )
    parser.add_argument("--count", type=int, default=8, metavar="N",
                        help="how many happy numbers to find (default: 8)")
    parser.add_argument("--check", type=int, metavar="N", help="test one number")
    parser.add_argument("--path", action="store_true", help="show the sequence for --check")
    parser.add_argument("--start", type=int, default=1, help="start searching at this number")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.check is not None:
        try:
            happy, path = happy_path(args.check)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"{args.check} is {'happy' if happy else 'unhappy'}")
        if args.path:
            print(" -> ".join(str(number) for number in path))
        if not happy:
            print("(the sequence loops without reaching 1)")
        return 0

    try:
        numbers = find_happy(args.count, start=args.start)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"First {args.count} happy numbers from {args.start}:")
    print(", ".join(str(number) for number in numbers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
