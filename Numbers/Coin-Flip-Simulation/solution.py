#!/usr/bin/env python3
"""Simulate flipping a coin many times and summarise the results.

Records every outcome, counts heads and tails, reports percentages and the
longest run of each side.  A seed makes runs reproducible; ``--p-heads``
allows a biased coin.

Examples:
    python3 solution.py --flips 1000 --seed 42
    python3 solution.py --flips 20 --sequence
    python3 solution.py --flips 500 --p-heads 0.75
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field


@dataclass
class FlipResult:
    """Outcomes of a simulation plus derived statistics."""

    outcomes: list[str] = field(default_factory=list)
    heads: int = 0
    tails: int = 0
    longest_heads: int = 0
    longest_tails: int = 0

    @property
    def total(self) -> int:
        return len(self.outcomes)


def simulate(flips: int, rng: random.Random, p_heads: float = 0.5) -> FlipResult:
    """Flip ``flips`` times, recording outcomes and streaks."""

    if flips < 1:
        raise ValueError("number of flips must be at least 1")
    if not 0.0 <= p_heads <= 1.0:
        raise ValueError("p-heads must be between 0 and 1")

    result = FlipResult(outcomes=[])
    current_heads = current_tails = 0
    for _ in range(flips):
        side = "H" if rng.random() < p_heads else "T"
        result.outcomes.append(side)
        if side == "H":
            result.heads += 1
            current_heads += 1
            current_tails = 0
            result.longest_heads = max(result.longest_heads, current_heads)
        else:
            result.tails += 1
            current_tails += 1
            current_heads = 0
            result.longest_tails = max(result.longest_tails, current_tails)
    return result


def sequence_text(outcomes: list[str], limit: int = 120) -> str:
    """Render outcomes, truncating very long runs."""

    if len(outcomes) <= limit:
        return " ".join(outcomes)
    return " ".join(outcomes[:limit]) + f" ... (+{len(outcomes) - limit} more)"


def print_summary(result: FlipResult, p_heads: float) -> None:
    """Print counts, percentages and streaks."""

    total = result.total
    print(f"Flips:        {total:,}")
    print(f"P(heads):     {p_heads:.2f}")
    print(f"Heads:        {result.heads:,} ({result.heads / total:.1%})")
    print(f"Tails:        {result.tails:,} ({result.tails / total:.1%})")
    print(f"Longest run:  heads {result.longest_heads}, tails {result.longest_tails}")


def run_demo() -> int:
    """Run a large seeded simulation and a short visible sequence."""

    print("Coin Flip Simulation demo")
    print("=" * 52)
    print("1,000 flips with seed 42:")
    result = simulate(1000, random.Random(42))
    print_summary(result, 0.5)
    print()

    print("20 flips with seed 7 (outcome sequence):")
    short = simulate(20, random.Random(7))
    print(f"  {sequence_text(short.outcomes)}")
    print(f"  heads={short.heads} tails={short.tails} "
          f"(longest streak H{short.longest_heads}/T{short.longest_tails})")
    print()

    print("Biased coin, p(heads)=0.75, 400 flips, seed 1:")
    biased = simulate(400, random.Random(1), p_heads=0.75)
    print_summary(biased, 0.75)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flip a coin N times and count heads and tails.",
    )
    parser.add_argument("-n", "--flips", type=int, default=100,
                        help="number of flips (default: 100)")
    parser.add_argument("--seed", type=int, help="random seed for reproducible runs")
    parser.add_argument("--p-heads", type=float, default=0.5, metavar="P",
                        help="probability of heads, 0.0-1.0 (default: 0.5)")
    parser.add_argument("--sequence", action="store_true",
                        help="print the full outcome sequence (truncated at 120)")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    flips = args.flips
    if flips is None:
        try:
            flips = int(input("How many flips? "))
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
        except ValueError:
            print("error: enter a whole number", file=sys.stderr)
            return 2

    try:
        result = simulate(flips, random.Random(args.seed), args.p_heads)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_summary(result, args.p_heads)
    if args.sequence:
        print(f"Sequence: {sequence_text(result.outcomes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
