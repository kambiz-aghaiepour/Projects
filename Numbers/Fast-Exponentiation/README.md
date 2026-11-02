# Fast Exponentiation

**Category:** Numbers · **Project:** `Fast-Exponentiation`

## Problem

> Ask the user to enter 2 integers a and b and output a^b (i.e. pow(a,b)) in O(lg n) time complexity.

## Features

- Binary exponentiation (exponentiation by squaring) in O(log b) multiplications.
- `--trace` shows every squaring and result multiplication step.
- Modular exponentiation with `--mod`, keeping intermediate values small.
- Negative exponents return exact `Fraction` results (`2^-3 = 1/8`).
- Handles `0`, `1`, negative bases and very large exponents (`2^100`).
- Reports the theoretical multiplication count and compares it with naive repeated
  multiplication (for `b = 1,000,000`: 25 vs 999,999).
- Cross-checks 50 random cases against Python's built-in `pow()` in the demo.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 3 13
python3 solution.py 3 13 --trace
python3 solution.py 4 13 --mod 497
python3 solution.py 2 -3
```

- `BASE` and `EXPONENT` — integers; prompted if omitted.
- `--mod M` — compute `a^b mod M`; requires a non-negative exponent and positive modulus.
- `--trace` — print each step of the square-and-multiply loop.
- `--demo` — trace `3^13`, show powers, negative exponents, modular cases and counts.

## Example Output

```text
Fast Exponentiation demo
==========================================================
Trace for 3^13:
start: result=1, base=3, exponent=13
  exponent odd -> result *= 3  => result=3
  square base => base=9, exponent=6
  square base => base=81, exponent=3
  exponent odd -> result *= 81  => result=243
  square base => base=6561, exponent=1
  exponent odd -> result *= 6561  => result=1594323
3^13 = 1594323

Powers:
  2^10 = 1024
  2^100 = 1267650600228229401496703205376
  (-7)^5 = -16807
  5^0 = 1
  7^1 = 7

Negative exponent:
  2^-3 = 1/8
  (-3)^-2 = 1/9

Modular exponentiation:
  4^13 mod 497 = 445
  2^1000 mod 1_000_000_007 = 688423210

Operation counts for b = 1,000,000:
  binary exponentiation: 25 multiplications
  naive repeated multiply: 999999 multiplications

Cross-check against pow() and naive multiplication for 50 random cases: pass
```

## Implementation Notes

The loop examines the exponent's bits from least significant to most:

1. If the current bit is 1, multiply the accumulator by the current base.
2. Square the base.
3. Shift the exponent right by one.

Each iteration halves the exponent, so there are `⌊log₂ b⌋` iterations. The
multiplication count is about `log₂ b` squarings plus `popcount(b) − 1` accumulator
multiplications. Python integers are arbitrary precision, so `fast_pow` returns
exact results; with `--mod`, every multiplication is reduced modulo `M`.

Negative exponents are exact rationals via `fractions.Fraction`, avoiding float
rounding. Python's built-in `pow(a, b, m)` implements the same algorithm in C and
is faster in practice; this project demonstrates the algorithm itself.
