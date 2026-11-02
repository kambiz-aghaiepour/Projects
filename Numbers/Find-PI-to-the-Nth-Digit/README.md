# Find PI to the Nth Digit

**Category:** Numbers · **Project:** `Find-PI-to-the-Nth-Digit`

## Problem

Enter a number and have the program generate PI up to that many decimal places. Keep a limit to how far the program will go.

## Features

- Generates π with 0–1000 decimal places, truncated rather than rounded.
- Uses the Chudnovsky series with `decimal.Decimal`; no binary floating point.
- Configurable hard cap via `--max-digits` (never above 1000).
- Validates negative, oversized and non-numeric input with clear messages.
- Interactive prompt when run without a digit argument.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 100
python3 solution.py 1000
python3 solution.py --max-digits 200 250   # rejected: above the lowered cap
```

- `DIGITS` — positional count of decimal places (0–1000).
- `--max-digits N` — lower the built-in 1000-digit ceiling.
- `--demo` — print 10-, 50- and 100-digit samples and exit.

## Example Output

```text
pi to various precisions (Chudnovsky series, truncated):
   10 decimals: 3.1415926535
   50 decimals: 3.14159265358979323846264338327950288419716939937510
  100 decimals: 3.1415926535897932384626433832795028841971693993751058209749445923078164062862089986280348253421170679

Hard limit: 1000 decimal places.
```

## Implementation Notes

The Chudnovsky series adds roughly 14 correct digits per term, so a request
for `n` digits needs `n // 14 + 3` terms. Arithmetic runs inside a
`localcontext` with `n + 12` digits of precision. The final digit is produced
one place beyond the request and dropped, which avoids rounding `3.999…` up to
`4.000…`. Results were checked against an independent Machin-formula
computation at 1000 digits.

Cost grows with Decimal multiplication, roughly O(n²) in the number of digits
at this scale. The 1000-digit cap keeps interactive use fast (well under a
second on a typical machine).
