# Fizz Buzz

*Category: **Text** · Project directory: `Text/Fizz-Buzz`*

## Problem

Write a program that prints the numbers from 1 to 100. But for multiples of three print "Fizz" instead of the number and for the multiples of five print "Buzz". For numbers which are multiples of both three and five print "FizzBuzz".

This version keeps the classic 1–100 behaviour but makes the range and the divisor/word rules configurable.

## Features

- Classic defaults: `3 → Fizz`, `5 → Buzz`, range `1..100`.
- Configurable inclusive range with `--start` and `--end`.
- Any number of custom rules using repeatable `--rule DIVISOR:LABEL`; a number matching several rules prints all labels in rule order (`15 → FizzBuzz`).
- Custom output separator (`--separator`) and optional file output (`--output`).
- Interactive range prompt when run with no arguments on a terminal.
- Validation for empty ranges, non-positive divisors, malformed rules, and duplicate divisors.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py                                  # 1..100, prompts for a range on a TTY
python3 solution.py --start 1 --end 15
python3 solution.py --rule 3:Fizz --rule 5:Buzz --rule 7:Pop --end 30
python3 solution.py --start 90 --end 100 --separator ", "
python3 solution.py --end 20 --output fizzbuzz.txt
```

Options:

- `--start N` / `--end N` — inclusive range (defaults 1 and 100).
- `--rule DIVISOR:LABEL` — add a rule; when at least one `--rule` is supplied it replaces the default Fizz/Buzz set. Repeat the flag for multiple rules.
- `--separator TEXT` — text placed between results; defaults to a newline.
- `--output FILE` — write the result to a file instead of stdout.
- `--demo` — scripted demonstration with no input.

## Example Output

```text
$ python3 solution.py --demo
Standard rules (Fizz=3, Buzz=5), 1 to 20:
1 2 Fizz 4 Buzz Fizz 7 8 Fizz Buzz 11 Fizz 13 14 FizzBuzz 16 17 Fizz 19 Buzz

Custom rules (3:Fizz, 5:Buzz, 7:Pop), 1 to 21:
1 2 Fizz 4 Buzz Fizz Pop 8 Fizz Buzz 11 Fizz 13 Pop FizzBuzz 16 17 Fizz 19 Buzz FizzPop

Rule spot checks:
   15 -> FizzBuzz
   21 -> FizzPop
   35 -> BuzzPop
```

## Implementation Notes

`fizz_buzz_value` joins the labels of every rule whose divisor divides the number and falls back to `str(number)` when none match. Generation is O(range × rules) time and O(range) output. Rules are stored as frozen dataclasses and duplicate divisors are rejected rather than silently overriding each other. Output is assembled in memory before printing, which keeps the separator logic simple; very large ranges should use `--output` or a narrower range.
