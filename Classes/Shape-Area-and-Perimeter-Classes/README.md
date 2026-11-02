# Shape Area and Perimeter Classes

## Problem

Create an abstract class called Shape and then inherit from it other shapes
like diamond, rectangle, circle, triangle etc. Then have each class override
the area and perimeter functionality to handle each shape type.

This is the **Classes / Shape Area and Perimeter Classes** project: an
exercise in abstract base classes, polymorphism, validation and comparison.

Project location: `Classes/Shape-Area-and-Perimeter-Classes/` (`README.md` and
`solution.py`).

## Features

- Abstract `Shape` base class declaring `area()`, `perimeter()` and
  `dimensions()`, plus shared display and JSON serialisation.
- Six concrete shapes:
  - `Circle(radius)`
  - `Rectangle(width, height)`
  - `Square(side)` — inherits the rectangle formulas
  - `Triangle(a, b, c)` — Heron's formula with the triangle inequality check
  - `Diamond(d1, d2)` — rhombus from its diagonals
  - `Trapezoid(base_a, base_b, height)` — isosceles trapezoid
- Strict validation: finite positive dimensions, valid triangles, clear errors
  for unknown shape names or wrong parameter counts.
- `ShapeReport` sorts by area, computes totals, counts by type, finds the
  largest/smallest shapes and the shape closest to a target area, and exports
  a JSON report.
- Two interfaces: positional `SHAPE:PARAMS` specs on the command line, or an
  interactive REPL when run with no arguments.

## Requirements

Python 3.10+. Standard library only (`math`, `json`, `argparse`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py "circle:2" "rectangle:3,4" "triangle:3,4,5"
python3 solution.py "diamond:6,8" "trapezoid:6,10,4" --json
python3 solution.py
```

Each spec is `name:value[,value...]`:

| Shape | Spec example | Parameters |
| --- | --- | --- |
| Circle | `circle:2` | radius |
| Rectangle | `rectangle:3,4` | width, height |
| Square | `square:2.5` | side |
| Triangle | `triangle:3,4,5` | side a, side b, side c |
| Diamond | `diamond:6,8` | long diagonal, short diagonal |
| Trapezoid | `trapezoid:6,10,4` | base a, base b, height |

Options: `--demo` runs the scripted tour; `--json` prints the full report as
JSON. With no specs and no `--demo`, an interactive prompt accepts lines such
as `circle 2`, `rectangle 3 4`, `triangle 3 4 5`, plus `list`, `report`,
`clear` and `quit`.

## Example Output

```text
=== Shape Area and Perimeter Classes: demo ===

Individual shapes:
  Circle(r=2)  area=12.5664  perimeter=12.5664
  Circle(r=1)  area=3.1416  perimeter=6.2832
  Rectangle(3 x 4)  area=12.0000  perimeter=14.0000
  Rectangle(5 x 2)  area=10.0000  perimeter=14.0000
  Square(side=2.5)  area=6.2500  perimeter=10.0000
  Triangle(3, 4, 5)  area=6.0000  perimeter=12.0000
  Diamond(d1=6, d2=8)  area=24.0000  perimeter=20.0000
  Trapezoid(bases 6/10, h=4)  area=32.0000  perimeter=24.9443

Area report (largest first):
Shape        Dimensions                                 Area    Perimeter
-------------------------------------------------------------------------
Trapezoid    bases 6/10, h=4                         32.0000      24.9443
Diamond      d1=6, d2=8                              24.0000      20.0000
Circle       r=2                                     12.5664      12.5664
Rectangle    3 x 4                                   12.0000      14.0000
Rectangle    5 x 2                                   10.0000      14.0000
Square       side=2.5                                 6.2500      10.0000
Triangle     3, 4, 5                                  6.0000      12.0000
Circle       r=1                                      3.1416       6.2832
-------------------------------------------------------------------------
TOTAL        8                                      105.9580     113.7938

Shapes: 8; types: Circle x2, Diamond x1, Rectangle x2, Square x1, Trapezoid x1, Triangle x1
Largest:  Trapezoid(bases 6/10, h=4)  area=32.0000  perimeter=24.9443
Smallest: Circle(r=1)  area=3.1416  perimeter=6.2832

Validation checks:
  negative radius: rejected -> radius must be a positive number, got -1
  zero width: rejected -> width must be a positive number, got 0
  impossible triangle: rejected -> sides 1, 2, 10 do not form a triangle (each pair must sum to more than the third side)
  unknown shape: rejected -> unknown shape 'hexagon'; choose from circle, rectangle, square, triangle, diamond, trapezoid
  wrong parameter count: rejected -> circle needs 1 value(s) (radius), got 2

JSON report: 1768 bytes, 8 shapes, total_area=105.9580

Demo complete.
```

## Implementation Notes

- Every shape validates in `__init__`, so an invalid object can never exist;
  `positive()` also rejects `nan`, `inf` and zero.
- Formulas:
  - Circle: `πr²`, `2πr`
  - Rectangle: `wh`, `2(w+h)`
  - Triangle: Heron `√(s(s-a)(s-b)(s-c))`, `a+b+c`
  - Diamond: `d1·d2/2`, `4·√((d1/2)²+(d2/2)²)`
  - Trapezoid: `(a+b)/2·h`; leg `√(h²+((b-a)/2)²)`, perimeter `a+b+2·leg`
- `Square` subclasses `Rectangle`, which demonstrates both inheritance and
  method reuse; it overrides `dimensions()` and `dimension_text()` so reports
  show a side rather than width/height.
- `ShapeReport` sorts a copy of the list, so the caller's collection is never
  mutated. All totals are recomputed from the shapes rather than cached.
- The report is a plain table for humans and a nested JSON object (`shapes`,
  `counts_by_type`, totals, largest, smallest) for scripts.
- Complexity is O(n log n) for the sorted table and O(n) for every statistic;
  there is no geometry beyond the closed-form formulas above (no coordinate
  geometry or arbitrary polygons).
