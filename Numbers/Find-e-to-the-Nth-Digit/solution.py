#!/usr/bin/env python3
"""Generate Euler's number e to a requested number of decimal places.

The value is computed from the Taylor series e = sum(1/k!) using
:class:`decimal.Decimal`, then truncated to the requested precision.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, localcontext

MAX_DIGITS = 1000
GUARD_DIGITS = 12


def e_to_digits(digits: int, max_digits: int = MAX_DIGITS) -> str:
    """Return e with exactly ``digits`` digits after the decimal point."""
    if digits < 0:
        raise ValueError("number of digits must be non-negative")
    if digits > max_digits:
        raise ValueError(f"requested {digits} digits, limit is {max_digits}")

    if digits == 0:
        return "2"

    with localcontext() as ctx:
        ctx.prec = digits + GUARD_DIGITS
        threshold = Decimal(1).scaleb(-(digits + GUARD_DIGITS))
        total = Decimal(1)
        term = Decimal(1)
        k = 0
        while term >= threshold:
            k += 1
            term /= k
            total += term
        value = total

    text = format(value, f".{digits + 1}f")
    return text[:-1]


def parse_digits(raw: str) -> int:
    """Parse a digit count with a friendly error message."""
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"not a whole number: {raw!r}") from exc
    if value < 0:
        raise ValueError("number of digits must be non-negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate e to N decimal places (maximum 1000).",
        epilog="Run with no arguments to be prompted for a digit count.",
    )
    parser.add_argument("digits", nargs="?", type=int, help="decimal places (0-1000)")
    parser.add_argument(
        "--max-digits",
        type=int,
        default=MAX_DIGITS,
        metavar="N",
        help=f"lower the hard cap (default: {MAX_DIGITS})",
    )
    parser.add_argument(
        "--demo", action="store_true", help="print sample values and exit"
    )
    return parser


def run_demo() -> int:
    """Print deterministic sample output."""
    print("e to various precisions (Taylor series, truncated):")
    for digits in (10, 50, 100):
        print(f"  {digits:>3} decimals: {e_to_digits(digits)}")
    print(f"\nHard limit: {MAX_DIGITS} decimal places.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_digits < 1 or args.max_digits > MAX_DIGITS:
        parser.error(f"--max-digits must be between 1 and {MAX_DIGITS}")

    if args.demo:
        return run_demo()

    digits = args.digits
    if digits is None:
        try:
            digits = parse_digits(input(f"Decimal places (0-{args.max_digits}): "))
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    try:
        print(e_to_digits(digits, args.max_digits))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
