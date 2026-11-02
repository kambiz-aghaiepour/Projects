# Limit Calculator

**Category:** Numbers · **Project:** `Limit-Calculator`

## Problem

> Ask the user to enter f(x) and the limit value, then return the value of the limit statement. Optional: Make the calculator capable of supporting infinite limits.

## Features

- Parses expressions safely with `ast`; only arithmetic, powers, `x`, constants
  (`pi`, `e`, `tau`) and a whitelist of math functions are allowed. No `eval`.
- Supports two-sided, left-hand and right-hand limits (`--dir`).
- Handles limits at `inf` and `-inf` as well as finite points.
- Detects finite limits, `+infinity`/`-infinity`, and limits that do not exist
  (jumps, opposite infinities, oscillation).
- Handles functions defined on only one side, such as `sqrt(x)` at 0.
- Accepts `^` or `**` for powers and `f(x) = ...` prefixes.
- `--samples` prints the raw h → f(x) table for inspection.
- Demo covers removable discontinuities, sinc, poles, limits at infinity and one-sided cases.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py "sin(x)/x" --at 0
python3 solution.py "(x**2 - 1)/(x - 1)" --at 1 --dir right
python3 solution.py "1/x" --at 0 --samples
python3 solution.py "(1 + 1/x)**x" --at inf
python3 solution.py --expr="-x" --at 0
```

- `EXPRESSION` — function of `x`; quote it to protect `*`, `(` and `)`.
- `-e/--expr EXPR` — same, useful when the expression starts with `-`.
- `--at POINT` — finite number, `inf` or `-inf` (default 0).
- `--dir {both,left,right}` — approach direction (default both).
- `--samples` — print the sampling table.
- `--demo` — evaluate the standard example set.
- With no expression, the program prompts for `f(x)` and the point.

## Example Output

```text
Limit Calculator demo
==============================================================
  (x**2 - 1)/(x - 1)           at 1    -> 2
  sin(x)/x                     at 0    -> 1
  1/x                          at 0    -> does not exist
  1/x**2                       at 0    -> infinity
  (1 + 1/x)**x                 at inf  -> 2.7182818
  (x**2 + 3*x)/(2*x**2 - x)    at inf  -> 0.5
  sqrt(x)                      at 0    -> 0
  abs(x)/x                     at 0    -> does not exist
  sin(x)                       at inf  -> does not exist

Details for 1/x as x -> 0:
  left-hand  = -infinity
  right-hand = infinity
  conclusion = does not exist (left and right limits are infinite with opposite signs)

Details for sqrt(x) as x -> 0:
  right-hand = 0
  conclusion = 0 (left-hand side is outside the domain)

Limit at infinity for (1 + 1/x)**x:
  estimate = 2.7182818 (e = 2.718281828)

One-sided example, (x**2 - 1)/(x - 1) as x -> 1 from the right:
  limit = 2
```

## Implementation Notes

This is a **numerical** limit estimator, not a computer-algebra system. For a
finite target `c`, it samples `f(c ± h)` for `h = 10⁻² … 10⁻⁵`, checks whether
values settle, and fits a local power-law model `f(c+h) ≈ L + a·h^p`. If the
fitted `p` is negative the side diverges (`±infinity`); a positive `p` allows the
finite `L` to be extrapolated. Limits at infinity sample `f(±10ᵏ)` instead.

Two-sided results combine the one-sided estimates: close finite values are
averaged, equal infinities are reported, and jumps, opposite infinities or
oscillation yield "does not exist". The fourth sample point validates the fitted
trend to catch oscillatory functions such as `sin(1/x)`.

Limitations: floating-point cancellation limits accuracy near very small `h`;
highly oscillatory functions can occasionally be mistaken for convergence; and
the tool cannot prove a limit symbolically. It is intended for interactive
exploration and standard textbook examples.
