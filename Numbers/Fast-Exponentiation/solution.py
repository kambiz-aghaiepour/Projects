#!/usr/bin/env python3
"""Fast exponentiation in O(log b) multiplications.

Raises two integers ``a`` and ``b`` using binary exponentiation, with an
optional modulus (modular exponentiation).  ``--trace`` shows every square
and multiply; the demo compares the operation count with naive repeated
multiplication.

Examples:
    python3 solution.py 3 13
    python3 solution.py 3 13 --trace
    python3 solution.py 4 13 --mod 497
    python3 solution.py 2 -3
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import random
import sys
from fractions import Fraction


def fast_pow(a: int, b: int, trace: list[str] | None = None) -> int:
    """Return ``a ** b`` for ``b >= 0`` using exponentiation by squaring."""

    if b < 0:
        raise ValueError("fast_pow expects a non-negative exponent")
    result = 1
    base = a
    exponent = b
    if trace is not None:
        trace.append(f"start: result=1, base={base}, exponent={exponent}")
    while exponent:
        if exponent & 1:
            result *= base
            if trace is not None:
                trace.append(f"  exponent odd -> result *= {base}  => result={result}")
        exponent >>= 1
        if exponent:
            base *= base
            if trace is not None:
                trace.append(f"  square base => base={base}, exponent={exponent}")
    return result


def fast_pow_signed(a: int, b: int) -> int | Fraction:
    """Return ``a ** b`` for any integer exponent, using a Fraction for b < 0."""

    if b >= 0:
        return fast_pow(a, b)
    if a == 0:
        raise ZeroDivisionError("0 cannot be raised to a negative power")
    result = Fraction(1, fast_pow(a, -b))
    return result.numerator if result.denominator == 1 else result


def fast_pow_mod(a: int, b: int, modulus: int) -> int:
    """Return ``a ** b mod modulus`` in O(log b) multiplications."""

    if modulus <= 0:
        raise ValueError("modulus must be positive")
    if b < 0:
        raise ValueError("modular exponentiation needs a non-negative exponent")
    result = 1
    base = a % modulus
    exponent = b
    while exponent:
        if exponent & 1:
            result = result * base % modulus
        exponent >>= 1
        if exponent:
            base = base * base % modulus
    return result % modulus


def naive_pow(a: int, b: int) -> int:
    """Reference implementation: multiply ``a`` by itself ``b`` times."""

    if b < 0:
        raise ValueError("naive_pow expects a non-negative exponent")
    result = 1
    for _ in range(b):
        result *= a
    return result


def operation_count_fast(b: int) -> int:
    """Number of multiplications used by binary exponentiation."""

    if b <= 0:
        return 0
    bits = b.bit_length()
    return (bits - 1) + bin(b).count("1") - 1


def format_number(value: int | Fraction) -> str:
    """Format integers in full and fractions as ``n/d``."""

    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    return str(value)


def power_text(base: int, exponent: int) -> str:
    """Render a power without ambiguity for negative bases."""

    return f"({base})^{exponent}" if base < 0 else f"{base}^{exponent}"


def run_demo() -> int:
    """Trace one power, show a table and compare algorithms."""

    print("Fast Exponentiation demo")
    print("=" * 58)
    trace: list[str] = []
    value = fast_pow(3, 13, trace)
    print("Trace for 3^13:")
    for line in trace:
        print(line)
    print(f"3^13 = {value}\n")

    print("Powers:")
    for base, exponent in ((2, 10), (2, 100), (-7, 5), (5, 0), (7, 1)):
        result = fast_pow(base, exponent)
        shown = str(result) if len(str(result)) <= 40 else f"{str(result)[:12]}... ({len(str(result))} digits)"
        print(f"  {power_text(base, exponent)} = {shown}")

    print("\nNegative exponent:")
    print(f"  {power_text(2, -3)} = {format_number(fast_pow_signed(2, -3))}")
    print(f"  {power_text(-3, -2)} = {format_number(fast_pow_signed(-3, -2))}")

    print("\nModular exponentiation:")
    print(f"  4^13 mod 497 = {fast_pow_mod(4, 13, 497)}")
    print(f"  2^1000 mod 1_000_000_007 = {fast_pow_mod(2, 1000, 1_000_000_007)}")

    print("\nOperation counts for b = 1,000,000:")
    print(f"  binary exponentiation: {operation_count_fast(1_000_000)} multiplications")
    print(f"  naive repeated multiply: {999_999} multiplications")

    rng = random.Random(1234)
    ok = True
    for _ in range(50):
        base = rng.randint(-9, 9)
        exponent = rng.randint(0, 8)
        expected = pow(base, exponent)
        if fast_pow(base, exponent) != expected or naive_pow(base, exponent) != expected:
            ok = False
    print(f"\nCross-check against pow() and naive multiplication for 50 random cases: "
          f"{'pass' if ok else 'FAIL'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute a^b with O(log b) exponentiation by squaring.",
    )
    parser.add_argument("base", nargs="?", type=int, help="integer base a")
    parser.add_argument("exponent", nargs="?", type=int, help="integer exponent b")
    parser.add_argument("--mod", type=int, metavar="M",
                        help="compute a^b mod M (exponent must be non-negative)")
    parser.add_argument("--trace", action="store_true", help="show each squaring step")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    base, exponent = args.base, args.exponent
    if base is None:
        try:
            base = int(input("Base a: "))
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        except ValueError:
            print("error: base must be an integer", file=sys.stderr)
            return 2
    if exponent is None:
        try:
            exponent = int(input("Exponent b: "))
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        except ValueError:
            print("error: exponent must be an integer", file=sys.stderr)
            return 2

    try:
        if args.mod is not None:
            result = fast_pow_mod(base, exponent, args.mod)
            print(f"{power_text(base, exponent)} mod {args.mod} = {result}")
        else:
            trace: list[str] = []
            if exponent >= 0:
                result = fast_pow(base, exponent, trace if args.trace else None)
            else:
                result = fast_pow_signed(base, exponent)
            print(f"{power_text(base, exponent)} = {format_number(result)}")
            if args.trace and exponent >= 0:
                print("\n".join(trace))
                print(f"multiplications: {operation_count_fast(exponent)}")
    except (ValueError, ZeroDivisionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
