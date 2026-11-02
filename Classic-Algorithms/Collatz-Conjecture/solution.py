#!/usr/bin/env python3
"""Explore the Collatz conjecture with a memoised step counter.

The Collatz process maps an even number ``n`` to ``n / 2`` and an odd number
``n`` to ``3n + 1``.  The conjecture states that every trajectory eventually
reaches 1.  This tool reports step counts and peaks for individual starting
values and finds the longest chain below a bound, reusing results through a
cache so repeated queries stay cheap.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

MAX_LIMIT = 5_000_000
MAX_DISPLAY = 24


@dataclass(frozen=True)
class Chain:
    """Summary of one Collatz trajectory."""

    start: int
    steps: int
    peak: int

    def describe(self) -> str:
        return f"start {self.start:,}: {self.steps} steps, peak {self.peak:,}"


class Collatz:
    """Memoised Collatz calculator.

    ``steps(n)`` fills the cache for every value on the trajectory, so a scan
    over a range performs close to one unit of work per new starting value.
    """

    def __init__(self) -> None:
        self._steps: dict[int, int] = {1: 0}
        self._peak: dict[int, int] = {1: 1}

    def steps(self, n: int) -> int:
        """Return the number of Collatz steps needed to reach 1 from *n*."""
        if n < 1:
            raise ValueError("n must be a positive integer")
        if n in self._steps:
            return self._steps[n]

        path: list[int] = []
        value = n
        while value not in self._steps:
            path.append(value)
            value = value // 2 if value % 2 == 0 else 3 * value + 1

        total = self._steps[value]
        peak = self._peak[value]
        for item in reversed(path):
            total += 1
            peak = max(peak, item)
            self._steps[item] = total
            self._peak[item] = peak
        return self._steps[n]

    def peak(self, n: int) -> int:
        """Return the largest value reached on the way from *n* to 1."""
        self.steps(n)
        return self._peak[n]

    def chain(self, n: int) -> list[int]:
        """Return the full trajectory from *n* down to 1 (inclusive)."""
        if n < 1:
            raise ValueError("n must be a positive integer")
        sequence = [n]
        while n != 1:
            n = n // 2 if n % 2 == 0 else 3 * n + 1
            sequence.append(n)
        return sequence

    def longest_under(self, limit: int) -> Chain:
        """Return the starting value in ``1..limit`` with the most steps."""
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        best = Chain(1, 0, 1)
        for start in range(2, limit + 1):
            steps = self.steps(start)
            if steps > best.steps:
                best = Chain(start, steps, self._peak[start])
        return best

    @property
    def cached_values(self) -> int:
        """Number of starting values currently held in the cache."""
        return len(self._steps)


def format_sequence(sequence: list[int]) -> str:
    """Render a trajectory, eliding the middle when it is long."""
    if len(sequence) <= MAX_DISPLAY:
        return " -> ".join(str(value) for value in sequence)
    head = " -> ".join(str(value) for value in sequence[:10])
    tail = " -> ".join(str(value) for value in sequence[-6:])
    omitted = len(sequence) - 16
    return f"{head} -> ... ({omitted:,} omitted) ... -> {tail}"


def run_demo(limit: int) -> int:
    """Print a scripted, deterministic Collatz demonstration."""
    solver = Collatz()
    print("Collatz Conjecture - demo")
    print("Rule: n even -> n/2, n odd -> 3n + 1; stop when the value reaches 1.")
    print()
    print("Steps for the first ten starting values:")
    for start in range(1, 11):
        print(f"  {start:>2} -> {solver.steps(start):>2} steps")

    print()
    print("Sample trajectories:")
    for start in (6, 27):
        sequence = solver.chain(start)
        print(f"  {start}: {format_sequence(sequence)}")
        print(f"     {solver.steps(start)} steps, peak {solver.peak(start):,}")

    print()
    best = solver.longest_under(limit)
    print(f"Longest chain for 1 <= n <= {limit:,}:")
    print(f"  {best.describe()}")
    print(f"  cache entries: {solver.cached_values:,}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Count Collatz steps and find the longest chain below a bound.",
        epilog="With no options, prompts for a starting number.",
    )
    parser.add_argument(
        "number",
        nargs="?",
        type=int,
        help="starting number (n >= 1); omit for interactive mode",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=100_000,
        help="upper bound for the longest-chain search in --demo (default: 100000)",
    )
    parser.add_argument(
        "-s",
        "--sequence",
        action="store_true",
        help="print the full trajectory for the requested number",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a scripted, non-interactive demonstration",
    )
    parser.add_argument(
        "--max-limit",
        action="store_true",
        help="just print the supported demo bound and exit",
    )
    return parser


def _read_int(prompt: str) -> int | None:
    """Prompt until an integer is entered; return None on end-of-input."""
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return None
        raw = raw.strip()
        if not raw:
            continue
        try:
            return int(raw)
        except ValueError:
            print("Please enter a whole number.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Program entry point.  Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_limit:
        print(f"Demo limit is capped at {MAX_LIMIT:,}.")
        return 0

    if args.demo:
        if not 1 <= args.limit <= MAX_LIMIT:
            print(
                f"--limit must be between 1 and {MAX_LIMIT:,}.",
                file=sys.stderr,
            )
            return 2
        return run_demo(args.limit)

    number = args.number
    if number is None:
        number = _read_int("Starting number (n >= 1): ")
        if number is None:
            print("No input received.", file=sys.stderr)
            return 1

    if number < 1:
        print("The starting number must be a positive integer.", file=sys.stderr)
        return 2

    solver = Collatz()
    chain = Chain(number, solver.steps(number), solver.peak(number))
    print(chain.describe())
    if args.sequence:
        sequence = solver.chain(number)
        print(format_sequence(sequence))
        print(f"trajectory length (including start): {len(sequence):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
