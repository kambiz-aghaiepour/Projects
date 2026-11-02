#!/usr/bin/env python3
"""Compute factorials with both iteration and recursion.

Factorials are exact Python integers.  The recursive version is deliberately
capped (default 900) because Python limits call-stack depth; the iterative
version handles very large ``n``.  The program also reports digit counts and
trailing zeros.

Examples:
    python3 solution.py 20
    python3 solution.py 100 --trailing-zeros
    python3 solution.py --table 15
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import math
import sys

MAX_RECURSIVE = 900
TABLE_LIMIT = 200


def parse_integer(text: str) -> int:
    """Parse ``5``, ``5!``, ``1_000`` or ``1,000`` into a non-negative int."""

    cleaned = text.strip().replace(",", "").replace("_", "")
    if cleaned.endswith("!"):
        cleaned = cleaned[:-1].strip()
    try:
        value = int(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid integer {text!r}") from exc
    if value < 0:
        raise ValueError("factorial is defined for non-negative integers only")
    return value


def factorial_iterative(n: int) -> int:
    """Return ``n!`` using a loop (O(n) multiplications)."""

    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    result = 1
    for factor in range(2, n + 1):
        result *= factor
    return result


def factorial_recursive(n: int) -> int:
    """Return ``n!`` using recursion; capped to stay within Python's stack."""

    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    if n > MAX_RECURSIVE:
        raise ValueError(f"recursive version is capped at n={MAX_RECURSIVE}; use the loop")
    if n <= 1:
        return 1
    return n * factorial_recursive(n - 1)


def trailing_zeros(n: int) -> int:
    """Count trailing zeros of ``n!`` with Legendre's formula."""

    zeros = 0
    power = 5
    while power <= n:
        zeros += n // power
        power *= 5
    return zeros


def trace_recursion(n: int) -> None:
    """Print the chain of recursive calls for a small factorial."""

    for value in range(n, 0, -1):
        suffix = f"{value} * {value - 1}!" if value > 1 else "1"
        print(f"  {value}! = {suffix}")
    print("  0! = 1 (base case)")


def describe(n: int) -> None:
    """Print one factorial with metadata."""

    value = factorial_iterative(n)
    print(f"{n}! = {value}")
    if n >= 25:
        digits = len(str(value))
        print(f"  digits: {digits:,}")
        print(f"  trailing zeros: {trailing_zeros(n)}")


def run_demo() -> int:
    """Show small factorials, both implementations and large-number metadata."""

    print("Factorial Finder demo")
    print("=" * 58)
    print("n! for n = 0..12 (iterative):")
    for n in range(13):
        print(f"  {n:>2}! = {factorial_iterative(n)}")

    print("\nRecursion trace for 5!:")
    trace_recursion(5)

    print("\nBoth implementations agree for n = 0..20:")
    mismatches = [n for n in range(21) if factorial_iterative(n) != factorial_recursive(n)]
    print(f"  {'yes' if not mismatches else 'no, mismatches: ' + str(mismatches)}")

    print("\nLarge factorials:")
    for n in (20, 25, 100, 1000):
        value = factorial_iterative(n)
        print(f"  {n:>4}! has {len(str(value)):>5} digits and "
              f"{trailing_zeros(n):>4} trailing zeros")

    print("\nIterative effort: n-1 multiplications")
    for n in (10, 100, 1000, 5000):
        print(f"  {n:>4}! -> {n - 1:>4} multiplications")

    print(f"\nRecursive implementation capped at n={MAX_RECURSIVE} "
          "(Python's default recursion limit).")
    print(f"math.factorial(20) agrees: {math.factorial(20) == factorial_iterative(20)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate factorials with loops or recursion.",
        epilog="Examples: solution.py 20 | solution.py '5!' | solution.py --table 15",
    )
    parser.add_argument("number", nargs="?", help="non-negative integer (optionally written as 5!)")
    parser.add_argument("--table", type=int, metavar="N", help="print a table of 0! through N!")
    parser.add_argument("--recursive", action="store_true",
                        help="also compute the result recursively")
    parser.add_argument("--trace", action="store_true", help="show the recursive call chain")
    parser.add_argument("--trailing-zeros", action="store_true",
                        help="show how many trailing zeros the factorial has")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.table is not None:
        if args.table < 0:
            parser.error("--table expects a non-negative integer")
        upper = min(args.table, TABLE_LIMIT)
        for n in range(upper + 1):
            print(f"{n:>3}! = {factorial_iterative(n)}")
        if args.table > TABLE_LIMIT:
            print(f"(table stops at {TABLE_LIMIT}; compute a single larger n directly)")
        return 0

    if args.number is None:
        print("Enter a non-negative integer (blank line to quit).")
        while True:
            try:
                line = input("n> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line.strip():
                return 0
            try:
                n = parse_integer(line)
                describe(n)
                if args.trailing_zeros:
                    print(f"  trailing zeros: {trailing_zeros(n)}")
                if args.recursive:
                    print(f"  recursive check: {n <= MAX_RECURSIVE}")
            except ValueError as exc:
                print(f"error: {exc}")
        return 0

    try:
        n = parse_integer(args.number)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        describe(n)
        if args.trailing_zeros:
            print(f"  trailing zeros: {trailing_zeros(n)}")
        if args.recursive:
            try:
                print(f"  recursive: {factorial_recursive(n)}")
            except ValueError as exc:
                print(f"  recursive: unavailable ({exc})")
        if args.trace:
            trace_recursion(min(n, 10))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
