# Calculator

**Category:** Numbers · **Project:** `Calculator`

## Problem

A simple calculator to do basic operators. Make it a scientific calculator for added complexity.

## Features

- Basic arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, `**` (or `^`).
- Scientific functions: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sinh`,
  `cosh`, `tanh`, `sqrt`, `cbrt`, `log`, `ln`, `log10`, `log2`, `exp`, `abs`,
  `floor`, `ceil`, `round`, `factorial`, `hypot`, `degrees`, `radians`.
- Constants `pi`, `e`, `tau`; parentheses and unary signs.
- `--degrees` switches trigonometric input/output to degrees.
- Interactive REPL plus repeatable `--expr` for scripts.
- Safe AST evaluation: no `eval`, imports, attributes or arbitrary calls.
- Friendly errors for division by zero, domain errors and rejected syntax.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --expr "2 + 3 * 4"
python3 solution.py --expr "sqrt(2)" --expr "log(1000, 10)"
python3 solution.py --degrees --expr "sin(30) + cos(60)"
python3 solution.py                       # interactive REPL
```

- `-e` / `--expr EXPR` — evaluate one expression (repeatable).
- `--degrees` — degrees for `sin`/`cos`/`tan` arguments and inverse-trig results.
- `--demo` — run arithmetic, scientific, degree-mode and rejection examples.
- No arguments starts a REPL; type `help` for the function list or `quit` to exit.

## Example Output

```text
Scientific calculator demo
=========================
  2 + 3 * 4            = 14
  (1 + 2) ^ 3          = 27
  sqrt(2)              = 1.41421356237
  log(1000, 10)        = 3
  factorial(5)         = 120
  pi * 2^2             = 12.5663706144
  hypot(3, 4)          = 5
  round(pi, 4)         = 3.1416
  2 ** 10              = 1024

Degree mode (trig arguments and inverse-trig results in degrees):
  sin(30)              = 0.5
  cos(60)              = 0.5
  atan(1)              = 45

Rejected inputs:
  1 / 0                -> error: division by zero
  __import__('os').getcwd() -> error: unsupported expression element: Attribute
  open('x')            -> error: function not allowed: 'open'
```

## Implementation Notes

The engine lives in `calc_engine.py`. Input is parsed with
`ast.parse(mode="eval")` and every node is checked against a whitelist of
expression, binary/unary operator, numeric constant, name and direct-call
nodes. Names must be known constants; calls must target a name in the function
table with no keywords. The evaluator then walks the validated tree itself, so
Python's `eval` is never involved.

Guard rails limit expressions to 500 characters, 200 AST nodes, factorials to
1000, and exponents to 10,000. Integer results print exactly; floats use 12
significant digits. `round` uses Python's float semantics, which can differ
from decimal half-up rounding at binary boundaries.
