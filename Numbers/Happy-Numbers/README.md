# Happy Numbers

**Category:** Numbers · **Project:** `Happy-Numbers`

## Problem

> A happy number is defined by the following process. Starting with any positive integer, replace the number by the sum of the squares of its digits, and repeat the process until the number equals 1 (where it will stay), or it loops endlessly in a cycle which does not include 1. Those numbers for which this process ends in 1 are happy numbers, while those that do not end in 1 are unhappy numbers. Find first 8 happy numbers.

## Features

- Finds the first 8 happy numbers by default: `1, 7, 10, 13, 19, 23, 28, 31`.
- `--count N` finds any number of them; `--start N` begins the search elsewhere.
- `--check N` tests a single number; `--path` shows its complete sequence.
- Cycle detection with a `set`, so unhappy numbers terminate instead of looping forever.
- Demonstrates the canonical unhappy cycle (`4 → 16 → 37 → … → 4`) and happy paths.
- Reports happy-number density for ranges up to 10,000.
- Handles arbitrarily large Python integers.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --count 8
python3 solution.py --count 20 --start 100
python3 solution.py --check 19 --path
python3 solution.py --check 4 --path
```

- `--count N` — how many happy numbers to find (default 8).
- `--start N` — first candidate to test (default 1).
- `--check N` — test one number and print happy/unhappy.
- `--path` — with `--check`, print the digit-square sequence.
- `--demo` — first eight numbers, two example paths and a density check.

## Example Output

```text
Happy Numbers demo
========================================================
First 8 happy numbers:
  1, 7, 10, 13, 19, 23, 28, 31

Why 19 is happy:
  19 -> 82 -> 68 -> 100 -> 1  (happy)

Why 4 is unhappy:
  4 -> 16 -> 37 -> 58 -> 89 -> 145 -> 42 -> 20 -> 4  (unhappy)
  detected cycle length: 8

Density check:
    20 happy numbers in 1..100 (20.0%)
   143 happy numbers in 1..1,000 (14.3%)
  1442 happy numbers in 1..10,000 (14.4%)

First 20 happy numbers: [1, 7, 10, 13, 19, 23, 28, 31, 32, 44, 49, 68, 70, 79, 82, 86, 91, 94, 97, 100]
```

## Implementation Notes

Each step replaces `n` by the sum of the squares of its decimal digits. The
sequence either reaches 1 or enters a cycle. A `set` of previously seen values
detects repetition in O(length) time; the maximum sequence length for numbers in
practical ranges is small (the unhappy cycle has period 8).

Searching the first `k` happy numbers examines roughly `k / 0.14` candidates,
since about 14% of positive integers are happy. The check is base-10 specific:
changing the base changes which numbers are happy.
