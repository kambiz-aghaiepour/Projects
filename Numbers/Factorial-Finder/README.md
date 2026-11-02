# Factorial Finder

**Category:** Numbers · **Project:** `Factorial-Finder`

## Problem

> The Factorial of a positive integer, n, is defined as the product of the sequence n, n-1, n-2, ...1 and the factorial of zero, 0, is defined as being 1. Solve this using both loops and recursion.

## Features

- Iterative and recursive implementations, both returning exact Python big integers.
- Correct base cases: `0! = 1! = 1`.
- Recursive version is capped at `n = 900` with a helpful message instead of a `RecursionError`.
- `--table N` prints a compact factorial table.
- `--trailing-zeros` uses Legendre's formula (`n/5 + n/25 + …`), not string counting.
- Digit counts and trailing-zero counts for large results such as `1000!`.
- `--trace` prints the recursive call chain for small inputs.
- Accepts `5!`, `1,000` and `1_000` as input forms.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 20
python3 solution.py 100 --trailing-zeros
python3 solution.py "5!" --recursive --trace
python3 solution.py --table 15
```

- `NUMBER` — non-negative integer, optionally written with a trailing `!`.
- `--table N` — print `0!` through `N!` (the table caps at 200 rows; compute larger values individually).
- `--recursive` — also compute (and compare) the recursive result.
- `--trace` — show the recursion chain, e.g. `5! = 5 * 4!`.
- `--trailing-zeros` — report how many zeros end the decimal representation.
- `--demo` — run the scripted comparison and metadata report.

## Example Output

```text
Factorial Finder demo
==========================================================
n! for n = 0..12 (iterative):
   0! = 1
   1! = 1
   2! = 2
   3! = 6
   4! = 24
   5! = 120
   6! = 720
   7! = 5040
   8! = 40320
   9! = 362880
  10! = 3628800
  11! = 39916800
  12! = 479001600

Recursion trace for 5!:
  5! = 5 * 4!
  4! = 4 * 3!
  3! = 3 * 2!
  2! = 2 * 1!
  1! = 1
  0! = 1 (base case)

Both implementations agree for n = 0..20:
  yes

Large factorials:
    20! has    19 digits and    4 trailing zeros
    25! has    26 digits and    6 trailing zeros
   100! has   158 digits and   24 trailing zeros
  1000! has  2568 digits and  249 trailing zeros

Iterative effort: n-1 multiplications
    10! ->    9 multiplications
   100! ->   99 multiplications
  1000! ->  999 multiplications
  5000! -> 4999 multiplications

Recursive implementation capped at n=900 (Python's default recursion limit).
math.factorial(20) agrees: True
```

## Implementation Notes

`n!` grows very quickly: `1000!` has 2568 digits. Python's integers are arbitrary
precision, so both implementations are exact. The loop performs `n-1`
multiplications; the cost is dominated by big-integer multiplication for large
`n`. The recursive version makes one Python call per factor and would exceed the
default recursion limit around `n ≈ 1000`, hence the explicit cap at 900.

Trailing zeros come from factors of 10, i.e. pairs of 2s and 5s; since factors of
2 are plentiful, Legendre's sum over powers of 5 gives the answer directly.
