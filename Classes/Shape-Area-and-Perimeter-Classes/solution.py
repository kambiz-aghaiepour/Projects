#!/usr/bin/env python3
"""Shape Area and Perimeter Classes.

An abstract ``Shape`` defines the area/perimeter contract.  Circle,
Rectangle, Square, Triangle, Diamond and Trapezoid implement it with their
own formulas and validation.  ``ShapeReport`` compares a collection of shapes
and renders a table or JSON summary.

Run ``python3 solution.py --demo`` for a scripted demonstration, or try::

    python3 solution.py "circle:2" "rectangle:3,4" "triangle:3,4,5"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Iterable, Optional


class ShapeError(ValueError):
    """Raised when a shape is given invalid dimensions."""


def positive(name: str, value: float) -> float:
    """Validate that *value* is a finite positive number."""
    if not math.isfinite(value) or value <= 0:
        raise ShapeError(f"{name} must be a positive number, got {value!r}")
    return value


class Shape(ABC):
    """Abstract geometric shape with an area and a perimeter."""

    label: ClassVar[str] = "Shape"

    @abstractmethod
    def area(self) -> float:
        """Return the enclosed area in square units."""

    @abstractmethod
    def perimeter(self) -> float:
        """Return the boundary length in linear units."""

    @abstractmethod
    def dimensions(self) -> dict[str, float]:
        """Return the constructor dimensions as a mapping."""

    def dimension_text(self) -> str:
        """Human-readable dimensions, e.g. ``r=2`` or ``3 x 4``."""
        return ", ".join(f"{key}={value:g}" for key, value in self.dimensions().items())

    def describe(self) -> str:
        return (f"{self.label}({self.dimension_text()})  "
                f"area={self.area():.4f}  perimeter={self.perimeter():.4f}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.label,
            "dimensions": self.dimensions(),
            "area": round(self.area(), 6),
            "perimeter": round(self.perimeter(), 6),
        }

    def __str__(self) -> str:
        return self.describe()


class Circle(Shape):
    """A circle defined by its radius."""

    label = "Circle"

    def __init__(self, radius: float) -> None:
        self.radius = positive("radius", radius)

    def area(self) -> float:
        return math.pi * self.radius ** 2

    def perimeter(self) -> float:
        return 2 * math.pi * self.radius

    def dimensions(self) -> dict[str, float]:
        return {"radius": self.radius}

    def dimension_text(self) -> str:
        return f"r={self.radius:g}"


class Rectangle(Shape):
    """An axis-aligned rectangle."""

    label = "Rectangle"

    def __init__(self, width: float, height: float) -> None:
        self.width = positive("width", width)
        self.height = positive("height", height)

    def area(self) -> float:
        return self.width * self.height

    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

    def dimensions(self) -> dict[str, float]:
        return {"width": self.width, "height": self.height}

    def dimension_text(self) -> str:
        return f"{self.width:g} x {self.height:g}"


class Square(Rectangle):
    """A rectangle with equal sides (inherits the rectangle formulas)."""

    label = "Square"

    def __init__(self, side: float) -> None:
        side = positive("side", side)
        super().__init__(side, side)
        self.side = side

    def area(self) -> float:
        return self.side ** 2

    def perimeter(self) -> float:
        return 4 * self.side

    def dimensions(self) -> dict[str, float]:
        return {"side": self.side}

    def dimension_text(self) -> str:
        return f"side={self.side:g}"


class Triangle(Shape):
    """A triangle defined by its three sides (Heron's formula)."""

    label = "Triangle"

    def __init__(self, a: float, b: float, c: float) -> None:
        self.a = positive("side a", a)
        self.b = positive("side b", b)
        self.c = positive("side c", c)
        if not (self.a + self.b > self.c and self.a + self.c > self.b
                and self.b + self.c > self.a):
            raise ShapeError(
                f"sides {a:g}, {b:g}, {c:g} do not form a triangle "
                "(each pair must sum to more than the third side)"
            )

    def area(self) -> float:
        s = self.perimeter() / 2
        return math.sqrt(s * (s - self.a) * (s - self.b) * (s - self.c))

    def perimeter(self) -> float:
        return self.a + self.b + self.c

    def dimensions(self) -> dict[str, float]:
        return {"a": self.a, "b": self.b, "c": self.c}

    def dimension_text(self) -> str:
        return f"{self.a:g}, {self.b:g}, {self.c:g}"


class Diamond(Shape):
    """A rhombus defined by its two diagonals."""

    label = "Diamond"

    def __init__(self, diagonal_long: float, diagonal_short: float) -> None:
        self.diagonal_long = positive("long diagonal", diagonal_long)
        self.diagonal_short = positive("short diagonal", diagonal_short)

    def area(self) -> float:
        return self.diagonal_long * self.diagonal_short / 2

    def perimeter(self) -> float:
        half_long = self.diagonal_long / 2
        half_short = self.diagonal_short / 2
        return 4 * math.hypot(half_long, half_short)

    def dimensions(self) -> dict[str, float]:
        return {"diagonal_long": self.diagonal_long, "diagonal_short": self.diagonal_short}

    def dimension_text(self) -> str:
        return f"d1={self.diagonal_long:g}, d2={self.diagonal_short:g}"


class Trapezoid(Shape):
    """An isosceles trapezoid defined by two bases and its height."""

    label = "Trapezoid"

    def __init__(self, base_a: float, base_b: float, height: float) -> None:
        self.base_a = positive("base a", base_a)
        self.base_b = positive("base b", base_b)
        self.height = positive("height", height)

    def leg(self) -> float:
        return math.hypot(self.height, (self.base_b - self.base_a) / 2)

    def area(self) -> float:
        return (self.base_a + self.base_b) / 2 * self.height

    def perimeter(self) -> float:
        return self.base_a + self.base_b + 2 * self.leg()

    def dimensions(self) -> dict[str, float]:
        return {"base_a": self.base_a, "base_b": self.base_b, "height": self.height}

    def dimension_text(self) -> str:
        return f"bases {self.base_a:g}/{self.base_b:g}, h={self.height:g}"


SHAPE_TYPES: dict[str, type[Shape]] = {
    "circle": Circle,
    "rectangle": Rectangle,
    "square": Square,
    "triangle": Triangle,
    "diamond": Diamond,
    "trapezoid": Trapezoid,
}

PARAMETER_NAMES: dict[str, tuple[str, ...]] = {
    "circle": ("radius",),
    "rectangle": ("width", "height"),
    "square": ("side",),
    "triangle": ("a", "b", "c"),
    "diamond": ("diagonal_long", "diagonal_short"),
    "trapezoid": ("base_a", "base_b", "height"),
}


def make_shape(kind: str, values: Iterable[float]) -> Shape:
    """Construct a shape from a type name and positional values."""
    key = kind.strip().lower()
    if key not in SHAPE_TYPES:
        raise ShapeError(f"unknown shape {kind!r}; choose from {', '.join(SHAPE_TYPES)}")
    numbers = list(values)
    expected = len(PARAMETER_NAMES[key])
    if len(numbers) != expected:
        raise ShapeError(
            f"{key} needs {expected} value(s) ({', '.join(PARAMETER_NAMES[key])}), "
            f"got {len(numbers)}"
        )
    return SHAPE_TYPES[key](*numbers)


def parse_spec(spec: str) -> Shape:
    """Parse a ``name:value,value`` specification into a shape."""
    if ":" not in spec:
        raise ShapeError(f"expected SHAPE:PARAMS, got {spec!r}")
    kind, raw = spec.split(":", 1)
    try:
        values = [float(part) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise ShapeError(f"non-numeric dimension in {spec!r}") from exc
    if not values:
        raise ShapeError(f"missing dimensions in {spec!r}")
    return make_shape(kind, values)


class ShapeReport:
    """Comparison table and aggregate statistics for a list of shapes."""

    def __init__(self, shapes: Iterable[Shape]) -> None:
        self.shapes = list(shapes)

    def __len__(self) -> int:
        return len(self.shapes)

    def sorted_by_area(self, reverse: bool = True) -> list[Shape]:
        return sorted(self.shapes, key=lambda shape: shape.area(), reverse=reverse)

    def largest(self) -> Shape:
        if not self.shapes:
            raise ShapeError("report is empty")
        return max(self.shapes, key=lambda shape: shape.area())

    def smallest(self) -> Shape:
        if not self.shapes:
            raise ShapeError("report is empty")
        return min(self.shapes, key=lambda shape: shape.area())

    def closest_to_area(self, target: float) -> Shape:
        if not self.shapes:
            raise ShapeError("report is empty")
        return min(self.shapes, key=lambda shape: abs(shape.area() - target))

    def counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for shape in self.shapes:
            totals[shape.label] = totals.get(shape.label, 0) + 1
        return dict(sorted(totals.items()))

    def total_area(self) -> float:
        return sum(shape.area() for shape in self.shapes)

    def total_perimeter(self) -> float:
        return sum(shape.perimeter() for shape in self.shapes)

    def table(self) -> str:
        if not self.shapes:
            return "(no shapes)"
        header = f"{'Shape':<12} {'Dimensions':<34} {'Area':>12} {'Perimeter':>12}"
        lines = [header, "-" * len(header)]
        for shape in self.sorted_by_area():
            lines.append(
                f"{shape.label:<12} {shape.dimension_text():<34} "
                f"{shape.area():>12.4f} {shape.perimeter():>12.4f}"
            )
        lines.append("-" * len(header))
        lines.append(f"{'TOTAL':<12} {len(self.shapes):<34} "
                     f"{self.total_area():>12.4f} {self.total_perimeter():>12.4f}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        if not self.shapes:
            return {"shapes": [], "count": 0, "total_area": 0, "total_perimeter": 0}
        return {
            "shapes": [shape.to_dict() for shape in self.shapes],
            "count": len(self.shapes),
            "counts_by_type": self.counts(),
            "total_area": round(self.total_area(), 6),
            "total_perimeter": round(self.total_perimeter(), 6),
            "largest": self.largest().to_dict(),
            "smallest": self.smallest().to_dict(),
        }

    def json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def run_demo() -> int:
    """Build a mixed set of shapes, compare them and show validation."""
    print("=== Shape Area and Perimeter Classes: demo ===\n")
    shapes: list[Shape] = [
        Circle(2),
        Circle(1),
        Rectangle(3, 4),
        Rectangle(5, 2),
        Square(2.5),
        Triangle(3, 4, 5),
        Diamond(6, 8),
        Trapezoid(6, 10, 4),
    ]

    print("Individual shapes:")
    for shape in shapes:
        print(f"  {shape.describe()}")

    report = ShapeReport(shapes)
    print("\nArea report (largest first):")
    print(report.table())

    print(f"\nShapes: {len(report)}; types: "
          + ", ".join(f"{name} x{count}" for name, count in report.counts().items()))
    print(f"Largest:  {report.largest().describe()}")
    print(f"Smallest: {report.smallest().describe()}")
    print(f"Total area {report.total_area():.4f}; "
          f"total perimeter {report.total_perimeter():.4f}")

    target = Circle(1).area()
    closest = report.closest_to_area(target)
    print(f"Closest area to Circle(radius=1) ({target:.4f}): {closest.describe()}")

    print("\nValidation checks:")
    checks = [
        ("negative radius", lambda: Circle(-1)),
        ("zero width", lambda: Rectangle(0, 4)),
        ("impossible triangle", lambda: Triangle(1, 2, 10)),
        ("unknown shape", lambda: make_shape("hexagon", [2, 3])),
        ("wrong parameter count", lambda: make_shape("circle", [1, 2])),
    ]
    for label, action in checks:
        try:
            action()
        except ShapeError as exc:
            print(f"  {label}: rejected -> {exc}")

    payload = report.json()
    decoded = json.loads(payload)
    print(f"\nJSON report: {len(payload)} bytes, "
          f"{len(decoded['shapes'])} shapes, total_area={decoded['total_area']:.4f}")
    print("\nDemo complete.")
    return 0


def _parse_specs(specs: list[str]) -> list[Shape]:
    return [parse_spec(spec) for spec in specs]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute area and perimeter for circles, rectangles, squares, "
                    "triangles, diamonds and trapezoids.",
        epilog='Examples: "circle:2"  "rectangle:3,4"  "triangle:3,4,5"  '
               '"diamond:6,8"  "trapezoid:6,10,4"',
    )
    parser.add_argument("specs", nargs="*", metavar="SHAPE:PARAMS",
                        help="shapes to compare, e.g. circle:2 rectangle:3,4")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def interactive() -> int:
    """REPL for building shapes and printing a live report."""
    print("Shape calculator. Enter shapes like 'circle 2' or 'rectangle 3 4'.")
    print("Commands: list, report, clear, help, quit.")
    shapes: list[Shape] = []
    while True:
        try:
            line = input("shape> ").strip()
        except EOFError:
            print()
            return 0
        if not line:
            continue
        command = line.lower()
        if command in {"quit", "exit", "q"}:
            return 0
        if command == "help":
            print("  circle RADIUS | rectangle WIDTH HEIGHT | square SIDE | "
                  "triangle A B C | diamond D1 D2 | trapezoid BASE_A BASE_B HEIGHT")
            continue
        if command == "list":
            print("\n".join(f"  {index}. {shape.describe()}"
                            for index, shape in enumerate(shapes, 1)) or "  (none)")
            continue
        if command == "report":
            print(ShapeReport(shapes).table())
            continue
        if command == "clear":
            shapes.clear()
            print("Cleared.")
            continue
        parts = line.replace(",", " ").split()
        try:
            shapes.append(make_shape(parts[0], [float(value) for value in parts[1:]]))
            print(f"  {shapes[-1].describe()}")
        except (ShapeError, ValueError) as exc:
            print(f"Error: {exc}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.specs:
        return interactive()

    try:
        shapes = _parse_specs(args.specs)
        report = ShapeReport(shapes)
    except ShapeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(report.json())
    else:
        print(report.table())
        print(f"\nLargest:  {report.largest().describe()}")
        print(f"Smallest: {report.smallest().describe()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
