#!/usr/bin/env python3
"""Find prime numbers one after another.

With no arguments the program prints successive primes and asks whether to
continue.  ``--count`` makes it non-interactive, which is also what
``--demo`` uses.
"""

from __future__ import annotations

import argparse
import sys

_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime(n: int) -> bool:
    """Return True when n is prime (deterministic Miller-Rabin for 64-bit n)."""
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

    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
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


def next_prime(after: int) -> int:
    """Return the smallest prime strictly greater than ``after``."""
    candidate = max(2, after + 1)
    if candidate <= 2:
        return 2
    if candidate % 2 == 0:
        candidate += 1
    while not is_prime(candidate):
        candidate += 2
    return candidate


def primes_from(start: int, count: int):
    """Yield ``count`` primes strictly greater than ``start``."""
    value = start
    for _ in range(count):
        value = next_prime(value)
        yield value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List prime numbers, interactively or by count.",
        epilog="Run with no arguments to keep asking for the next prime.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        metavar="N",
        help="begin after this number (default: 1)",
    )
    parser.add_argument(
        "--count",
        type=int,
        metavar="N",
        help="print N primes and exit instead of prompting",
    )
    parser.add_argument(
        "--demo", action="store_true", help="print scripted prime runs and exit"
    )
    return parser


def interactive(start: int) -> int:
    """Print primes until the user declines or input ends."""
    print("Press Enter to see the next prime, or type 'q' to quit.")
    current = start
    while True:
        try:
            answer = input("next? ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if answer.strip().lower() in {"q", "quit", "n", "no", "stop"}:
            return 0
        current = next_prime(current)
        print(current)


def run_demo() -> int:
    """Show sequential primes and a run near one million."""
    print("First 10 primes:")
    print(", ".join(str(p) for p in primes_from(1, 10)))
    print("\nNext 5 primes after 1,000,000:")
    print(", ".join(str(p) for p in primes_from(1_000_000, 5)))
    print("\nTwin prime pairs below 100:")
    previous = 2
    pairs = []
    for prime in primes_from(2, 25):
        if prime - previous == 2:
            pairs.append((previous, prime))
        previous = prime
    print(", ".join(f"({a}, {b})" for a, b in pairs if b < 100))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.count is not None and args.count < 1:
        parser.error("--count must be at least 1")
    if args.start < 0:
        parser.error("--start must be non-negative")

    if args.demo:
        return run_demo()

    if args.count is not None:
        for prime in primes_from(args.start, args.count):
            print(prime)
        return 0

    return interactive(args.start)


if __name__ == "__main__":
    raise SystemExit(main())
