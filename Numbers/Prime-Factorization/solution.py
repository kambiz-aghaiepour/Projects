#!/usr/bin/env python3
"""Factor a positive integer into primes.

Trial division handles small factors; leftover cofactors go through a
deterministic Miller-Rabin test and Pollard's rho, so 64-bit inputs and
moderate big integers (say, two 12-digit primes) factor quickly.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter

_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def is_prime(n: int) -> bool:
    """Deterministic Miller-Rabin for n < 3.3e24; probabilistic above."""
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p

    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    # These bases are deterministic for n < 3,317,044,064,679,887,385,961,981.
    bases = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for a in bases:
        if a >= n:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _pollard_rho(n: int) -> int:
    """Return a non-trivial factor of composite n (Brent's variant)."""
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3

    c = 1
    while True:
        y, r, q, g = 2, 1, 1, 1
        x = ys = y
        while g == 1:
            x = y
            for _ in range(r):
                y = (y * y + c) % n
            k = 0
            while k < r and g == 1:
                ys = y
                for _ in range(min(128, r - k)):
                    y = (y * y + c) % n
                    q = q * abs(x - y) % n
                g = math.gcd(q, n)
                k += 128
            r *= 2
        if g == n:
            g = 1
            while g == 1:
                ys = (ys * ys + c) % n
                g = math.gcd(abs(x - ys), n)
        if g != n:
            return g
        c += 1


def factorize(n: int) -> Counter[int]:
    """Return the prime factorization of |n| as a Counter of prime -> exponent."""
    if n == 0:
        raise ValueError("zero has no prime factorization")
    n = abs(n)
    factors: list[int] = []
    for p in _SMALL_PRIMES:
        while n % p == 0:
            factors.append(p)
            n //= p

    stack = [n] if n > 1 else []
    while stack:
        value = stack.pop()
        if value == 1:
            continue
        if is_prime(value):
            factors.append(value)
            continue
        divisor = _pollard_rho(value)
        stack.extend((divisor, value // divisor))
    return Counter(factors)


def format_factors(factors: Counter[int], original: int) -> str:
    """Render a factorization as ``2^3 * 3 * 5`` with a sign for negatives."""
    if not factors:
        return "-1" if original < 0 else "1"
    parts = []
    if original < 0:
        parts.append("-1")
    for prime in sorted(factors):
        exponent = factors[prime]
        parts.append(str(prime) if exponent == 1 else f"{prime}^{exponent}")
    return " * ".join(parts)


def parse_integer(raw: str) -> int:
    """Parse an integer allowing underscores and thousands separators."""
    cleaned = raw.strip().replace("_", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"not an integer: {raw!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print the prime factorization of an integer.",
        epilog="Run with no arguments to be prompted for a number.",
    )
    parser.add_argument("number", nargs="?", help="integer to factor")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument(
        "--demo", action="store_true", help="factor scripted examples and exit"
    )
    return parser


def emit(number: int, as_json: bool) -> None:
    """Factor one number and print the result."""
    factors = factorize(number)
    text = format_factors(factors, number)
    if as_json:
        print(
            json.dumps(
                {
                    "number": number,
                    "factorization": text,
                    "factors": [
                        {"prime": p, "exponent": factors[p]}
                        for p in sorted(factors)
                    ],
                }
            )
        )
    else:
        print(f"{number} = {text}")


def run_demo() -> int:
    """Factor a spread of inputs, including a large semiprime."""
    samples = [360, 97, 1024, 600851475143, -84, (10**9 + 7) * (10**9 + 9)]
    print("Prime factorizations:")
    for number in samples:
        emit(number, as_json=False)
    print("\nSame data as JSON for 360:")
    emit(360, as_json=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    raw = args.number
    try:
        if raw is None:
            raw = input("Number to factor: ")
        number = parse_integer(raw)
        emit(number, args.json)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (ValueError, RecursionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
