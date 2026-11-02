#!/usr/bin/env python3
"""Generate pi to a requested number of decimal places.

Uses the Chudnovsky series with Python's :class:`decimal.Decimal` for
arbitrary-precision arithmetic.  The output is truncated (not rounded) to the
requested number of digits after the decimal point.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, localcontext

MAX_DIGITS = 1000
GUARD_DIGITS = 12


def pi_to_digits(digits: int, max_digits: int = MAX_DIGITS) -> str:
    """Return pi with exactly ``digits`` digits after the decimal point.

    Raises:
        ValueError: if ``digits`` is negative or exceeds ``max_digits``.
    """
    if digits < 0:
        raise ValueError("number of digits must be non-negative")
    if digits > max_digits:
        raise ValueError(f"requested {digits} digits, limit is {max_digits}")

    if digits == 0:
        return "3"

    with localcontext() as ctx:
        ctx.prec = digits + GUARD_DIGITS
        # Chudnovsky: 1/pi = 12 * sum((-1)^k (6k)! (13591409 + 545140134k))
        #                    / ((3k)! (k!)^3 (640320)^(3k+3/2))
        constant = Decimal(426880) * Decimal(10005).sqrt()
        m = Decimal(1)
        l = Decimal(13591409)
        x = Decimal(1)
        k = Decimal(6)
        series = Decimal(13591409)
        for i in range(1, digits // 14 + 3):
            m = (k**3 - 16 * k) * m / (i**3)
            l += 545140134
            x *= -262537412640768000
            series += (m * l) / x
            k += 12
        pi = constant / series

    # One extra digit, then drop it: truncation avoids rounding 3.999 -> 4.000.
    text = format(pi, f".{digits + 1}f")
    return text[:-1]


def parse_digits(raw: str) -> int:
    """Parse a digit count, raising ValueError with a friendly message."""
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"not a whole number: {raw!r}") from exc
    if value < 0:
        raise ValueError("number of digits must be non-negative")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate pi to N decimal places (maximum 1000).",
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
    print("pi to various precisions (Chudnovsky series, truncated):")
    for digits in (10, 50, 100):
        print(f"  {digits:>3} decimals: {pi_to_digits(digits)}")
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
        print(pi_to_digits(digits, args.max_digits))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
