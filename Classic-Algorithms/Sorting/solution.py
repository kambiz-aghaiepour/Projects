#!/usr/bin/env python3
"""Merge sort and bubble sort implemented from scratch.

Both algorithms accept an injectable comparison callable, which lets the demo
report exact comparison counts.  This module never calls ``sorted`` or
``list.sort``; the only ordering primitive is the ``less`` predicate.
"""

from __future__ import annotations

import argparse
import operator
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Sequence

Number = int | float
Less = Callable[[Number, Number], bool]


class Comparisons:
    """Counting wrapper around a strict-less-than predicate."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, left: Number, right: Number) -> bool:
        self.count += 1
        return left < right


def merge_sort(values: Sequence[Number], less: Less = operator.lt) -> list[Number]:
    """Return a new list sorted with a stable top-down merge sort."""
    items = list(values)
    if len(items) <= 1:
        return items
    middle = len(items) // 2
    left = merge_sort(items[:middle], less)
    right = merge_sort(items[middle:], less)
    return _merge(left, right, less)


def _merge(left: list[Number], right: list[Number], less: Less) -> list[Number]:
    """Merge two sorted lists, preserving the order of equal elements."""
    merged: list[Number] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if less(right[j], left[i]):
            merged.append(right[j])
            j += 1
        else:
            merged.append(left[i])
            i += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged


def bubble_sort(values: Sequence[Number], less: Less = operator.lt) -> list[Number]:
    """Return a new list sorted with an early-exit bubble sort."""
    items = list(values)
    for end in range(len(items) - 1, 0, -1):
        swapped = False
        for index in range(end):
            if less(items[index + 1], items[index]):
                items[index], items[index + 1] = items[index + 1], items[index]
                swapped = True
        if not swapped:
            break
    return items


def is_sorted(values: Sequence[Number]) -> bool:
    """Return True when values are in non-decreasing order."""
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def parse_values(tokens: Sequence[str]) -> list[Number]:
    """Parse comma- or whitespace-separated numbers from CLI tokens."""
    text = " ".join(tokens).strip()
    parts = [part for part in re.split(r"[,\s]+", text) if part]
    if not parts:
        raise ValueError("no numbers supplied")
    values: list[Number] = []
    for part in parts:
        try:
            values.append(int(part))
        except ValueError:
            try:
                values.append(float(part))
            except ValueError as exc:
                raise ValueError(f"not a number: {part!r}") from exc
    return values


def format_numbers(values: Sequence[Number], limit: int = 30) -> str:
    """Render numbers on one line, eliding long lists."""
    shown = ", ".join(f"{value:g}" if isinstance(value, float) else str(value)
                      for value in values[:limit])
    if len(values) > limit:
        shown += f", ... ({len(values) - limit} more)"
    return shown


@dataclass(frozen=True)
class SortResult:
    """Outcome of one sorting run."""

    name: str
    values: list[Number]
    comparisons: int
    seconds: float


def _run(name: str, algorithm: Callable[[Sequence[Number], Less], list[Number]],
         values: Sequence[Number]) -> SortResult:
    comparator = Comparisons()
    start = time.perf_counter()
    ordered = algorithm(values, comparator)
    elapsed = time.perf_counter() - start
    return SortResult(name, ordered, comparator.count, elapsed)


def _verify(original: Sequence[Number], result: SortResult) -> bool:
    """Check sortedness and that no element was lost or invented."""
    ok = is_sorted(result.values) and Counter(original) == Counter(result.values)
    status = "ok" if ok else "FAILED"
    print(f"  verification ({result.name}): {status}")
    return ok


def run_demo(seed: int, benchmark: int) -> int:
    """Print a scripted demonstration on fixed and seeded data."""
    fixed = [38, 27, 43, 3, 9, 82, 10, -5, 27, 0]
    print("Sorting - demo")
    print(f"Input: {format_numbers(fixed)}")

    bubble = _run("bubble", bubble_sort, fixed)
    merge = _run("merge", merge_sort, fixed)
    print()
    for result in (bubble, merge):
        print(f"{result.name.capitalize()} sort: {format_numbers(result.values)}")
        print(f"  comparisons: {result.comparisons}")
    print(f"  outputs agree: {'yes' if bubble.values == merge.values else 'no'}")
    ok = _verify(fixed, bubble)
    ok = _verify(fixed, merge) and ok

    print()
    rng = random.Random(seed)
    bench_values = [rng.randint(0, 100_000) for _ in range(benchmark)]
    print(f"Benchmark on {benchmark:,} seeded integers (seed={seed}):")
    for name, algorithm in (("bubble", bubble_sort), ("merge", merge_sort)):
        result = _run(name, algorithm, bench_values)
        print(
            f"  {name:<6} {result.seconds:7.3f}s  {result.comparisons:>12,} comparisons"
            f"  sorted={is_sorted(result.values)}"
        )

    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sort numbers with hand-written merge sort and bubble sort.",
        epilog="Examples: solution.py 5 3 9 1   |   solution.py -a merge 4,2,7",
    )
    parser.add_argument(
        "values",
        nargs="*",
        help="numbers to sort, separated by spaces and/or commas",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        choices=("merge", "bubble", "both"),
        default="both",
        help="which algorithm to run (default: both)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a scripted, non-interactive demonstration",
    )
    parser.add_argument(
        "--benchmark",
        type=int,
        metavar="N",
        help="benchmark both algorithms on N random integers instead of sorting values",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20240101,
        help="random seed for the benchmark (default: 20240101)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point.  Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.benchmark is not None:
        if args.benchmark < 0:
            parser.error("--benchmark must be non-negative")
        return run_demo(args.seed, args.benchmark)

    if args.demo:
        return run_demo(args.seed, 600)

    if not args.values:
        try:
            raw = input("Numbers to sort (space or comma separated): ")
        except EOFError:
            print("No input received.", file=sys.stderr)
            return 1
        tokens = [raw]
    else:
        tokens = list(args.values)

    try:
        values = parse_values(tokens)
    except ValueError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2

    algorithms = {
        "merge": [("merge", merge_sort)],
        "bubble": [("bubble", bubble_sort)],
        "both": [("merge", merge_sort), ("bubble", bubble_sort)],
    }[args.algorithm]

    results = [_run(name, algorithm, values) for name, algorithm in algorithms]
    for result in results:
        print(f"{result.name} sort: {format_numbers(result.values)}")
        print(f"  comparisons: {result.comparisons:,}  time: {result.seconds:.4f}s")
    checks = [_verify(values, result) for result in results]
    if not all(checks):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
