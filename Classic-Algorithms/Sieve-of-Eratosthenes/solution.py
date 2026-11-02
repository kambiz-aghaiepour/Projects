#!/usr/bin/env python3
"""Sieve of Eratosthenes for prime generation up to ten million.

The sieve marks composites with a ``bytearray`` and slice assignment, which
moves the inner loop into C and keeps even the 10,000,000 case well under a
second.  A ``1`` byte means "prime", so counting is a fast ``sum``.
"""

from __future__ import annotations

import argparse
import math
import sys
import time

MAX_LIMIT = 10_000_000


def sieve(limit: int) -> bytearray:
    """Return a bytearray of length ``limit + 1`` with 1 for primes."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    flags = bytearray(b"\x01") * (limit + 1)
    flags[0] = 0
    if limit >= 1:
        flags[1] = 0
    for candidate in range(2, math.isqrt(limit) + 1):
        if flags[candidate]:
            start = candidate * candidate
            count = (limit - start) // candidate + 1
            flags[start::candidate] = b"\x00" * count
    return flags


def primes_from(flags: bytearray) -> list[int]:
    """Extract the prime indices from a sieve."""
    return [value for value, is_prime in enumerate(flags) if is_prime]


def count_primes(flags: bytearray) -> int:
    """Count primes in a sieve without materialising the list."""
    return sum(flags)


def is_prime(value: int, flags: bytearray) -> bool:
    """Check a value against an existing sieve."""
    return 0 <= value < len(flags) and bool(flags[value])


def twin_primes(flags: bytearray, gap: int = 2) -> list[tuple[int, int]]:
    """Return pairs of consecutive primes separated by exactly *gap*."""
    pairs: list[tuple[int, int]] = []
    previous: int | None = None
    for value, is_prime in enumerate(flags):
        if not is_prime:
            continue
        if previous is not None and value - previous == gap:
            pairs.append((previous, value))
        previous = value
    return pairs


def format_numbers(values: list[int], limit: int = 25) -> str:
    shown = ", ".join(str(value) for value in values[:limit])
    if len(values) > limit:
        shown += f", ... ({len(values) - limit:,} more)"
    return shown


def run_demo() -> int:
    """Print a scripted demonstration with timings and known counts."""
    print("Sieve of Eratosthenes - demo")
    print(f"Supported limit: up to {MAX_LIMIT:,}")
    print()

    small = sieve(50)
    print("Primes up to 50:")
    print(" ", format_numbers(primes_from(small)))

    print()
    print("Prime counting and timing:")
    print(f"  {'limit':>10}  {'primes':>8}  {'time':>8}  {'memory':>8}")
    total_time = 0.0
    for limit in (100_000, 1_000_000, 10_000_000):
        start = time.perf_counter()
        flags = sieve(limit)
        count = count_primes(flags)
        elapsed = time.perf_counter() - start
        total_time += elapsed
        memory_mb = len(flags) / (1024 * 1024)
        print(f"  {limit:>10,}  {count:>8,}  {elapsed:>7.3f}s  {memory_mb:>6.1f}MB")
        if limit == 10_000_000:
            largest = flags.rfind(b"\x01")
            print(f"  largest prime below {limit:,}: {largest:,}")

    print()
    print("Known checks: pi(100)=25, pi(1,000)=168, pi(1,000,000)=78,498")
    print(f"  pi(100) = {count_primes(sieve(100))}")
    print(f"  pi(10,000) = {count_primes(sieve(10_000)):,}")
    print(f"  prime 9973? {is_prime(9973, sieve(10_000))}; "
          f"prime 9999? {is_prime(9999, sieve(10_000))}")

    pairs = twin_primes(sieve(1_000))
    print()
    print(f"Twin primes below 1,000: {len(pairs)}; last five: "
          f"{' '.join(f'({a},{b})' for a, b in pairs[-5:])}")
    print(f"Demo sieve time (all three sizes): {total_time:.3f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate primes with the Sieve of Eratosthenes.",
        epilog="Example: solution.py --limit 1000000 --count",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=None,
        help="upper bound, inclusive (default: prompt; demo uses fixed sizes)",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="print only the number of primes and the largest one",
    )
    parser.add_argument(
        "--twin",
        action="store_true",
        help="also list twin prime pairs up to the limit",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a scripted, non-interactive demonstration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point.  Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    limit = args.limit
    if limit is None:
        try:
            raw = input("Upper bound for the sieve: ")
        except EOFError:
            print("No input received.", file=sys.stderr)
            return 1
        try:
            limit = int(raw)
        except ValueError:
            print("Please enter a whole number.", file=sys.stderr)
            return 2

    if limit < 0:
        print("--limit must be non-negative.", file=sys.stderr)
        return 2
    if limit > MAX_LIMIT:
        print(
            f"--limit is capped at {MAX_LIMIT:,} to keep memory use modest.",
            file=sys.stderr,
        )
        return 2

    start = time.perf_counter()
    flags = sieve(limit)
    elapsed = time.perf_counter() - start
    count = count_primes(flags)

    if args.count:
        largest = flags.rfind(b"\x01")
        print(f"primes <= {limit:,}: {count:,}")
        print(f"largest: {largest:,}" if largest >= 0 else "largest: none")
    else:
        values = primes_from(flags)
        print(format_numbers(values, limit=1000))
        print(f"primes <= {limit:,}: {count:,}")

    print(f"sieve time: {elapsed:.4f}s")
    if args.twin:
        pairs = twin_primes(flags)
        print(f"twin prime pairs: {len(pairs):,}")
        if pairs:
            print("last five:", " ".join(f"({a},{b})" for a, b in pairs[-5:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
