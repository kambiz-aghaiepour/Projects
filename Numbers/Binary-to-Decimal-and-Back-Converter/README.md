# Binary to Decimal and Back Converter

**Category:** Numbers · **Project:** `Binary-to-Decimal-and-Back-Converter`

## Problem

Develop a converter to convert a decimal number to binary or a binary number to its decimal equivalent.

## Features

- Decimal → binary and binary → decimal in both interactive and flag modes.
- Handles signs, fractional values and `0b` binary prefixes.
- Fractional decimal values are truncated at a configurable bit count, with a
  note when the representation is not exact.
- Optional digit grouping in blocks of four for readability.
- Accepts underscores and thousands separators in decimal input.
- Rejects malformed binary strings with a clear error.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --to-binary 10.625
python3 solution.py --to-decimal 1010.101
python3 solution.py --to-binary 3054 --group
python3 solution.py --to-binary 0.1 --places 32
```

- `--to-binary DECIMAL` — convert a decimal value to binary.
- `--to-decimal BINARY` — convert a binary value to decimal.
- `--places N` — maximum fraction bits for decimal → binary (default 16).
- `--group` — group binary digits in blocks of four.
- `--demo` — run the scripted examples.
- With no flags, the program asks for a direction and a value.

## Example Output

```text
Decimal -> binary
       42 -> 101010
   10.625 -> 1010.101
     -0.5 -> -0.1
      0.1 -> 0.00011001100110011001  (truncated at 20 fraction bits)
      255 -> 11111111

Binary -> decimal
        101010 -> 42
      1010.101 -> 10.625
          -0.1 -> -0.5
    0b11111111 -> 255

Grouped presentation
  3054 -> 1011 1110 1110
```

## Implementation Notes

The integer part uses Python's `format(n, "b")`. The fraction is converted by
repeatedly multiplying by two and taking the integer digit; any residue after
the allowed number of bits marks the result inexact. Binary → decimal builds
the integer part with `int(text, 2)` and sums `bit / 2^i` for fraction bits
inside a `Decimal` context sized to the input, so long fractions keep their
precision.

Grouping pads nothing and leaves the sign outside the first group. The
converter is a numeral-base tool only: it does not perform arithmetic on the
converted values or apply two's-complement representation to negative numbers.
