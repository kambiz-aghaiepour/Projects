# Find e to the Nth Digit

**Category:** Numbers · **Project:** `Find-e-to-the-Nth-Digit`

## Problem

Just like the previous problem, but with e instead of PI. Enter a number and have the program generate e up to that many decimal places. Keep a limit to how far the program will go.

## Features

- Generates Euler's number e with 0–1000 decimal places, truncated.
- Taylor series `e = Σ 1/k!` evaluated with `decimal.Decimal`.
- Stops as soon as the next term is below the precision guard.
- Configurable hard cap via `--max-digits` (maximum 1000).
- Interactive prompt when no digit argument is supplied.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 50
python3 solution.py 1000
```

- `DIGITS` — positional count of decimal places (0–1000).
- `--max-digits N` — lower the built-in 1000-digit ceiling.
- `--demo` — print 10-, 50- and 100-digit samples and exit.

## Example Output

```text
e to various precisions (Taylor series, truncated):
   10 decimals: 2.7182818284
   50 decimals: 2.71828182845904523536028747135266249775724709369996
  100 decimals: 2.7182818284590452353602874713526624977572470936999595749669676277240766303535475945713821785251664274

Hard limit: 1000 decimal places.
```

## Implementation Notes

Each iteration divides the previous term by `k` and adds it to the running
total. The loop stops when the term drops below `10^-(n+12)`, leaving more
than enough guard digits; the result is then truncated at `n` places by
formatting with `n + 1` decimals and dropping the last character.

The series converges very quickly (about 450 terms suffice for 1000 digits),
so the dominant cost is Decimal addition at high precision. The value was
cross-checked against an integer-scaled factorial sum at 1000 digits.
