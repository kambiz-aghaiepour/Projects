# Next Prime Number

**Category:** Numbers · **Project:** `Next-Prime-Number`

## Problem

Have the program find prime numbers until the user chooses to stop asking for the next one.

## Features

- Interactive mode: press Enter for the next prime, or `q` to stop.
- Non-interactive `--count N` mode for scripts and tests.
- `--start N` begins searching after any non-negative integer.
- Deterministic Miller–Rabin primality test with small-prime trial division.
- Demo also finds twin-prime pairs below 100.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py                 # interactive
python3 solution.py --count 20
python3 solution.py --start 1000000 --count 5
```

- `--start N` — search for primes strictly greater than N (default 1).
- `--count N` — print N primes and exit without prompting.
- `--demo` — print three scripted runs.

## Example Output

```text
First 10 primes:
2, 3, 5, 7, 11, 13, 17, 19, 23, 29

Next 5 primes after 1,000,000:
1000003, 1000033, 1000037, 1000039, 1000081

Twin prime pairs below 100:
(3, 5), (5, 7), (11, 13), (17, 19), (29, 31), (41, 43), (59, 61), (71, 73)
```

## Implementation Notes

Candidates are tested with the twelve-base Miller–Rabin test, which is
deterministic for integers below 3.3 × 10²⁴; small primes are divided out
before the modular exponentiation. Even candidates are skipped, so each search
step advances by two.

Finding the next prime after `n` uses Miller–Rabin on odd candidates, so each
test costs O(log³ n) modular multiplications and composites are rejected
quickly. The gap between consecutive primes near n is O(log n) on average,
making a full search inexpensive at practical sizes.
