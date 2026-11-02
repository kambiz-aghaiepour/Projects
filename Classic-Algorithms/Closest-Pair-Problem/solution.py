#!/usr/bin/env python3
"""Closest pair of points in the plane using O(n log n) divide and conquer.

Points are split by x-coordinate; each half is solved recursively and returns
its points sorted by y so the strip check can be done in linear time.  A
brute-force implementation is included as an independent cross-check for the
demo and for small inputs.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Sequence

Point = tuple[float, float]


@dataclass(frozen=True)
class ClosestPair:
    """Result of a closest-pair search."""

    distance: float
    first: Point | None
    second: Point | None
    distance_checks: int

    def describe(self) -> str:
        if self.first is None or self.second is None:
            return "no pair (fewer than two points)"
        return (
            f"{_fmt_point(self.first)} <-> {_fmt_point(self.second)} "
            f"distance {self.distance:.6f} ({self.distance_checks:,} checks)"
        )


def _fmt_point(point: Point) -> str:
    return f"({point[0]:g}, {point[1]:g})"


def _dist2(left: Point, right: Point) -> float:
    """Squared Euclidean distance (avoids square roots in inner loops)."""
    dx = left[0] - right[0]
    dy = left[1] - right[1]
    return dx * dx + dy * dy


def _brute(points: Sequence[Point]) -> tuple[float, Point | None, Point | None, int]:
    """Squared-distance brute force over all pairs."""
    best = math.inf
    first: Point | None = None
    second: Point | None = None
    checks = 0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            checks += 1
            candidate = _dist2(points[i], points[j])
            if candidate < best:
                best, first, second = candidate, points[i], points[j]
    return best, first, second, checks


def brute_force(points: Sequence[Point]) -> ClosestPair:
    """Reference O(n^2) implementation used for cross-checking."""
    items = list(points)
    if len(items) < 2:
        raise ValueError("need at least two points")
    best, first, second, checks = _brute(items)
    return ClosestPair(math.sqrt(best), first, second, checks)


def _merge_by_y(left: list[Point], right: list[Point]) -> list[Point]:
    """Merge two y-sorted point lists in linear time."""
    merged: list[Point] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i][1] <= right[j][1]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged


def _rec(px: list[Point]) -> tuple[float, Point | None, Point | None, int, list[Point]]:
    """Solve a strip of points sorted by x; also return them sorted by y."""
    size = len(px)
    if size <= 3:
        best, first, second, checks = _brute(px)
        return best, first, second, checks, sorted(px, key=lambda point: point[1])

    middle = size // 2
    mid_x = px[middle][0]
    left = _rec(px[:middle])
    right = _rec(px[middle:])
    checks = left[3] + right[3] + 1

    if left[0] <= right[0]:
        best, first, second = left[0], left[1], left[2]
    else:
        best, first, second = right[0], right[1], right[2]

    by_y = _merge_by_y(left[4], right[4])

    if best > 0.0:
        strip = [point for point in by_y if abs(point[0] - mid_x) < best]
        for i in range(len(strip)):
            j = i + 1
            while j < len(strip) and strip[j][1] - strip[i][1] < best:
                checks += 1
                candidate = _dist2(strip[i], strip[j])
                if candidate < best:
                    best, first, second = candidate, strip[i], strip[j]
                j += 1
    return best, first, second, checks, by_y


def closest_pair(points: Sequence[Point]) -> ClosestPair:
    """Find the closest pair of 2-D points in O(n log n) time."""
    items = sorted(points)
    if len(items) < 2:
        raise ValueError("need at least two points")
    best, first, second, checks, _ = _rec(items)
    return ClosestPair(math.sqrt(best), first, second, checks)


def parse_points(text: str) -> list[Point]:
    """Parse ``x,y`` tokens separated by whitespace, commas, or semicolons."""
    tokens = [token for token in re.split(r"[;\s]+", text.strip()) if token]
    if not tokens:
        raise ValueError("no points supplied")
    points: list[Point] = []
    for token in tokens:
        parts = token.strip("()").split(",")
        if len(parts) != 2:
            raise ValueError(f"bad point {token!r}; expected 'x,y'")
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError as exc:
            raise ValueError(f"bad coordinates in {token!r}") from exc
    return points


def run_demo(seed: int, random_count: int) -> int:
    """Print a scripted demonstration including a brute-force cross-check."""
    fixed: list[Point] = [
        (2, 3), (12, 30), (40, 50), (5, 1), (12, 10), (3, 4), (28, 19),
    ]
    print("Closest Pair - demo (O(n log n) divide and conquer)")
    print("Points:", " ".join(_fmt_point(point) for point in fixed))

    fast = closest_pair(fixed)
    reference = brute_force(fixed)
    print(f"  divide and conquer: {fast.describe()}")
    print(f"  brute force:        {reference.describe()}")
    matches = abs(fast.distance - reference.distance) < 1e-12
    print(f"  results agree: {'yes' if matches else 'NO'}")

    rng = random.Random(seed)
    cloud = [(rng.uniform(0.0, 1000.0), rng.uniform(0.0, 1000.0))
             for _ in range(random_count)]
    print()
    print(f"Random cloud: {random_count:,} points, seed={seed}")

    start = time.perf_counter()
    fast_cloud = closest_pair(cloud)
    fast_time = time.perf_counter() - start

    start = time.perf_counter()
    reference_cloud = brute_force(cloud)
    brute_time = time.perf_counter() - start

    cloud_matches = abs(fast_cloud.distance - reference_cloud.distance) < 1e-9
    print(f"  divide and conquer: {fast_cloud.describe()} in {fast_time:.4f}s")
    print(f"  brute force:        {reference_cloud.describe()} in {brute_time:.4f}s")
    print(f"  results agree: {'yes' if cloud_matches else 'NO'}")
    print(f"  speed-up at this size: {brute_time / fast_time:.1f}x")

    big = [(rng.uniform(0.0, 10_000.0), rng.uniform(0.0, 10_000.0))
           for _ in range(20_000)]
    start = time.perf_counter()
    big_result = closest_pair(big)
    big_time = time.perf_counter() - start
    print()
    print(f"Scaling check: 20,000 points in {big_time:.3f}s "
          f"(closest distance {big_result.distance:.4f})")

    return 0 if matches and cloud_matches else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find the closest pair of 2-D points with divide and conquer.",
        epilog="Example: solution.py --points '0,0 3,4 10,10'",
    )
    parser.add_argument(
        "-p",
        "--points",
        metavar="LIST",
        help="points as x,y tokens, e.g. '0,0 3,4 10,10'",
    )
    parser.add_argument(
        "--random",
        type=int,
        metavar="N",
        help="generate N random points instead of supplying them",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="random seed for --random and the demo (default: 12345)",
    )
    parser.add_argument(
        "--brute-force",
        action="store_true",
        help="use the O(n^2) reference algorithm instead of divide and conquer",
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
        return run_demo(args.seed, 400)

    if args.points:
        try:
            points = parse_points(args.points)
        except ValueError as exc:
            print(f"Invalid points: {exc}", file=sys.stderr)
            return 2
    elif args.random is not None:
        if args.random < 2:
            print("--random needs at least 2 points.", file=sys.stderr)
            return 2
        rng = random.Random(args.seed)
        points = [(rng.uniform(0, 1000), rng.uniform(0, 1000))
                  for _ in range(args.random)]
    else:
        try:
            raw = input("Points as x,y separated by spaces: ")
        except EOFError:
            print("No input received.", file=sys.stderr)
            return 1
        try:
            points = parse_points(raw)
        except ValueError as exc:
            print(f"Invalid points: {exc}", file=sys.stderr)
            return 2

    if len(points) < 2:
        print("At least two points are required.", file=sys.stderr)
        return 2

    try:
        result = brute_force(points) if args.brute_force else closest_pair(points)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(result.describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
