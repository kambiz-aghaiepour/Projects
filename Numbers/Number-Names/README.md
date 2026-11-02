# Number Names

**Category:** Numbers · **Project:** `Number-Names`

## Problem

> Show how to spell out a number in English. You can use a preexisting implementation or roll your own, but you should support inputs up to at least one million (or the maximum value of your language's default bounded integer type, if that's less). Optional: support zero, negative integers, and floating-point numbers.

## Features

- Spells integers from zero up to `10³⁶ − 1` (decillions), far beyond the required million.
- Handles negatives (`minus forty-two`) and decimals (`three point one four`).
- Reads decimal digits individually and preserves trailing zeros: `3.140` →
  "three point one four zero".
- Optional British style with `--and`: `101` → "one hundred and one",
  `1001` → "one thousand and one".
- Hyphenates compound tens (`twenty-one`) and separates scale groups with commas.
- Accepts commas and underscores in the input (`1,234,567`).
- Interactive mode when no numbers are given on the command line.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 1234567
python3 solution.py -42 3.14
python3 solution.py 1001 --and
python3 solution.py 1234567890123
```

- `NUMBERS...` — one or more numbers to spell out (integers or decimals).
- `--and` — include "and" after hundreds and before a final sub-hundred group.
- `--demo` — print the example table in both styles.
- With no numbers, the program reads them interactively until a blank line.

## Example Output

```text
Number Names demo
==========================================================
                 0 -> zero
                 7 -> seven
                21 -> twenty-one
               100 -> one hundred
               101 -> one hundred one
               999 -> nine hundred ninety-nine
              1000 -> one thousand
             12345 -> twelve thousand, three hundred forty-five
           1000000 -> one million
               -42 -> minus forty-two
              3.14 -> three point one four
     1234567890123 -> one trillion, two hundred thirty-four billion, five hundred sixty-seven million, eight hundred ninety thousand, one hundred twenty-three

British 'and' style:
               101 -> one hundred and one
              1001 -> one thousand and one
           1234567 -> one million, two hundred and thirty-four thousand, five hundred and sixty-seven

Decimals keep every written digit:
              0.05 -> zero point zero five
             3.140 -> three point one four zero
               2.5 -> two point five
       1000000.001 -> one million point zero zero one

Supported range: |n| < 1,000,000,000,000,000,000,000,000,000,000,000,000 (up to decillions).
```

## Implementation Notes

The number is split into groups of three digits from the right. Each group is
spelled with the hundreds/tens/ones vocabulary and suffixed with its short-scale
name (`thousand`, `million`, `billion`, … `decillion`). Values at or above
`10³⁶` are rejected with an explicit error rather than silently truncated.

Decimals are handled as `Decimal` strings, not binary floats, so `3.140` keeps
its three fractional digits. Digits after the point are read one at a time, as is
conventional in English. Commas between scale groups improve readability but are
otherwise cosmetic.
