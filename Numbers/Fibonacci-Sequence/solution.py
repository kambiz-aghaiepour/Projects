#!/usr/bin/env python3
"""Generate the Fibonacci sequence by term count or by maximum value.

Supports arbitrary-size integers and both "first N terms" and "all terms up
to V" interpretations of the classic prompt.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterator


def fibonacci(count: int | None = None, max_value: int | None = None) -> Iterator[int]:
    """Yield Fibonacci numbers.

    With ``count``, yield that many terms starting at F(0) = 0.
    With ``max_value``, yield every term less than or equal to the bound.
    Exactly one of the arguments must be supplied.
    """
    if (count is None) == (max_value is None):
        raise ValueError("supply exactly one of count or max_value")
    if count is not None and count < 0:
        raise ValueError("count must be non-negative")
    if max_value is not None and max_value < 0:
        raise ValueError("max_value must be non-negative")

    a, b = 0, 1
    if count is not None:
        for _ in range(count):
            yield a
            a, b = b, a + b
        return

    assert max_value is not None  # guaranteed by the check above
    while a <= max_value:
        yield a
        a, b = b, a + b


def nth_fibonacci(n: int) -> int:
    """Return F(n) using fast doubling, in O(log n) multiplications."""
    if n < 0:
        raise ValueError("n must be non-negative")

    def _pair(k: int) -> tuple[int, int]:
        if k == 0:
            return 0, 1
        a, b = _pair(k // 2)
        c = a * (2 * b - a)
        d = a * a + b * b
        if k % 2:
            return d, c + d
        return c, d

    return _pair(n)[0]


def parse_positive(raw: str, label: str) -> int:
    """Parse a non-negative integer with a clear error."""
    try:
        value = int(raw.strip().replace("_", "").replace(",", ""))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{label} must be a whole number: {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the Fibonacci sequence by count or by value.",
        epilog="Examples: solution.py 10 | solution.py --up-to 1000",
    )
    parser.add_argument("n", nargs="?", type=int, help="number of terms to print")
    parser.add_argument(
        "--up-to", type=int, metavar="V", help="print all terms less than or equal to V"
    )
    parser.add_argument(
        "--nth", type=int, metavar="N", help="print only F(N) using fast doubling"
    )
    parser.add_argument(
        "--no-index", action="store_true", help="omit the F(i) = prefix on each line"
    )
    parser.add_argument(
        "--demo", action="store_true", help="print scripted examples and exit"
    )
    return parser


def print_terms(terms: Iterator[int], show_index: bool) -> None:
    """Print a sequence, one term per line, optionally indexed."""
    for index, value in enumerate(terms):
        print(f"F({index}) = {value}" if show_index else str(value))


def run_demo() -> int:
    """Show both modes plus a large term."""
    print("First 15 Fibonacci numbers:")
    print_terms(fibonacci(count=15), show_index=True)
    print("\nFibonacci numbers less than or equal to 100:")
    print(", ".join(str(v) for v in fibonacci(max_value=100)))
    print("\nF(1000) via fast doubling:")
    print(nth_fibonacci(1000))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    try:
        if args.nth is not None:
            if args.n is not None or args.up_to is not None:
                parser.error("--nth cannot be combined with N or --up-to")
            print(nth_fibonacci(args.nth))
            return 0

        if args.up_to is not None:
            if args.n is not None:
                parser.error("give either N or --up-to, not both")
            print_terms(fibonacci(max_value=args.up_to), not args.no_index)
            return 0

        if args.n is not None:
            print_terms(fibonacci(count=args.n), not args.no_index)
            return 0

        raw = input("How many Fibonacci numbers? ")
        count = parse_positive(raw, "count")
        print_terms(fibonacci(count=count), not args.no_index)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
