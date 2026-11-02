# Prime Factorization

**Category:** Numbers · **Project:** `Prime-Factorization`

## Problem

Have the user enter a number and find all Prime Factors (if there are any) and display them.

## Features

- Factors positive and negative integers; reports `-1` for the sign.
- Trial division for small primes, deterministic Miller–Rabin for primality,
  and Pollard's rho (Brent variant) for large composite cofactors.
- Displays compact exponent notation such as `2^3 * 3^2 * 5`.
- `--json` output with the prime/exponent pairs.
- Handles 0, 1, malformed input and very large integers with clear errors.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 360
python3 solution.py 600851475143
python3 solution.py -84 --json
```

- `NUMBER` — integer to factor; commas and underscores are accepted.
- `--json` — emit a machine-readable result.
- `--demo` — factor a spread of values, including a 19-digit semiprime.

## Example Output

```text
Prime factorizations:
360 = 2^3 * 3^2 * 5
97 = 97
1024 = 2^10
600851475143 = 71 * 839 * 1471 * 6857
-84 = -1 * 2^2 * 3 * 7
1000000016000000063 = 1000000007 * 1000000009

Same data as JSON for 360:
{"number": 360, "factorization": "2^3 * 3^2 * 5", "factors": [{"prime": 2, "exponent": 3}, {"prime": 3, "exponent": 2}, {"prime": 5, "exponent": 1}]}
```

## Implementation Notes

Small primes are divided out first. Each remaining cofactor is tested with
Miller–Rabin using the twelve bases that make the test deterministic below
3.3 × 10²⁴; composite values are split with Pollard's rho until every piece is
prime. Factors are collected in a `Counter` and sorted for display.

Pollard's rho is probabilistic in general and can be slow for pathological
semiprimes with very large factors; deterministic bases remove randomness from
this implementation's results. Zero is rejected because it has no prime
factorization, while 1 prints as `1` (the empty product).
