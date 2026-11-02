# Reverse a String

*Category: **Text** · Project directory: `Text/Reverse-a-String`*

## Problem

Enter a string and the program will reverse it and print it out.

Beyond plain character reversal, this implementation offers word-order and line-order reversal, plus grapheme-aware reversal so accented letters and emoji sequences are not torn apart.

## Features

- Reverse by Unicode code point (the default, exact string reversal).
- `--graphemes` keeps combining accents, emoji modifiers, zero-width-joiner sequences, keycaps, and flag pairs intact.
- `--mode words` reverses word order while normalising whitespace.
- `--mode lines` reverses line order.
- Input from `--text`, a UTF-8 file (`--file`), piped stdin, or an interactive prompt.
- Useful error message and exit code 1 for unreadable or undecodable files.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --text 'Hello, world!'
python3 solution.py --text 'the quick brown fox' --mode words
python3 solution.py --text 'café' --graphemes
printf 'first\nsecond\nthird\n' | python3 solution.py --mode lines
python3 solution.py --file poem.txt --mode words
```

Options:

- `--text TEXT` — reverse a literal string.
- `--file PATH` — read text from a file (one trailing newline is stripped).
- `--mode {chars,words,lines}` — what to reverse; default `chars`.
- `--graphemes` — in `chars` mode, reverse visual characters rather than code points.
- `--encoding NAME` — file encoding, default UTF-8.
- `--demo` — scripted demonstration with no input.

## Example Output

```text
$ python3 solution.py --demo
Reversal examples:
  chars     'Hello, world!'                              -> '!dlrow ,olleH'
  words     'the quick brown fox'                        -> 'fox brown quick the'
  lines     'first line\nsecond line\nthird line'        -> 'third line\nsecond line\nfirst line'
  chars     'café'                                       -> 'éfac'

Code points vs grapheme clusters (decomposed 'e' + accent):
  code points: '\u0301e'
  graphemes:   'e\u0301'

Emoji sequence (family) reversed with --graphemes:
  !👩‍👩‍👧‍👦
```

With the decomposed `e` + combining acute accent, code-point reversal puts the accent before the letter; grapheme reversal keeps them together. The family emoji (four people joined by zero-width joiners) survives `--graphemes` reversal as one unit.

## Implementation Notes

Character reversal uses Python's slice `text[::-1]`, which operates on code points. `grapheme_clusters` implements a pragmatic subset of UAX #29: it extends a cluster for combining marks (`Mn`/`Me`/`Mc` or nonzero combining class), variation selectors, emoji skin-tone modifiers, keycaps, and anything following a zero-width joiner, and it pairs regional-indicator symbols into flags. Word reversal uses `str.split()` and rejoins with single spaces, so original spacing is not preserved in `words` mode; line reversal preserves each line's content but not a distinction between `\n` and `\r\n`. All modes run in O(n) time and O(n) space. Complex scripts with Indic conjuncts or emoji tag sequences are only approximated.
