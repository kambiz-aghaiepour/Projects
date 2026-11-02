# Count Vowels

*Category: **Text** · Project directory: `Text/Count-Vowels`*

## Problem

Enter a string and the program counts the number of vowels in the text. For added complexity have it report a sum of each vowel found.

This version reports each vowel's count and its share of both all vowels and all letters, and can optionally count `y`.

## Features

- Per-vowel counts for `a`, `e`, `i`, `o`, `u` (plus `y` with `--include-y`).
- Percentages relative to total vowels and relative to total letters.
- Totals for characters, letters, vowels, and consonants.
- Case-insensitive by design (`A` and `a` count together); works on Unicode text while counting the English vowel set.
- `--json` for machine-readable output.
- Input from `--text`, a UTF-8 file, piped stdin, or an interactive prompt.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --text 'Hello there'
python3 solution.py --file essay.txt
python3 solution.py --include-y --text 'rhythm and rhyme'
cat notes.txt | python3 solution.py --json
```

Options:

- `--text TEXT` — analyse a literal string.
- `--file PATH` — read text from a UTF-8 file.
- `--include-y` — count `y` as a vowel (adds a `y` row).
- `--json` — emit the full report as JSON instead of a table.
- `--encoding NAME` — file encoding, default UTF-8.
- `--demo` — scripted demonstration with no input.

## Example Output

```text
$ python3 solution.py --demo
Default vowels (a, e, i, o, u):
Text:       'The quick brown fox jumps over the lazy dog.'
Characters: 44  |  Letters: 35  |  Vowels: 11  |  Consonants: 24

Vowel   Count    % of vowels   % of letters
-------------------------------------------
a           1           9.1%           2.9%
e           3          27.3%           8.6%
i           1           9.1%           2.9%
o           4          36.4%          11.4%
u           2          18.2%           5.7%
-------------------------------------------
Total      11         100.0%          31.4%

With --include-y (y counted as a vowel):
Text:       'Myth: rhythm and rhyme rarely fly by.'
Characters: 37  |  Letters: 29  |  Vowels: 10  |  Consonants: 19

Vowel   Count    % of vowels   % of letters
-------------------------------------------
a           2          20.0%           6.9%
e           2          20.0%           6.9%
i           0           0.0%           0.0%
o           0           0.0%           0.0%
u           0           0.0%           0.0%
y           6          60.0%          20.7%
-------------------------------------------
Total      10         100.0%          34.5%
```

The demo also prints a short JSON excerpt; it is omitted here for brevity.

## Implementation Notes

The text is lowercased and scanned once; a `Counter` accumulates vowel frequencies. Letters are counted with `str.isalpha()`, so accented and non-Latin letters count as letters even though only ASCII `aeiou` (+ optional `y`) are recognised as vowels. Rounding is to one decimal place, and percentages are computed against the actual totals, so a text with no vowels reports `0.0` rather than dividing by zero. Time and space are O(n) in the input length.
