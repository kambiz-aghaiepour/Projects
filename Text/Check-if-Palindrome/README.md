# Check if Palindrome

*Category: **Text** · Project directory: `Text/Check-if-Palindrome`*

## Problem

Checks if the string entered by the user is a palindrome. That is that it reads the same forwards as backwards like "racecar".

Real-world palindromes are usually phrases, so the default check ignores case, punctuation, whitespace, and accents while still supporting strict raw comparison.

## Features

- Phrase-aware checking: `"A man, a plan, a canal: Panama"` passes.
- Normalisation drops punctuation and whitespace, case-folds letters, and strips combining accents via Unicode NFKD.
- `--exact` compares the raw text verbatim.
- `--case-sensitive` keeps case but still ignores punctuation and spacing.
- `--keep-accents` preserves accents during normalisation.
- Reports the normalised text, its length, and the first mismatching character pair.
- Input from `--text`, a UTF-8 file, piped stdin, or an interactive prompt.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --text 'racecar'
python3 solution.py --text 'A man, a plan, a canal: Panama'
python3 solution.py --text 'La mariée ira mal'
python3 solution.py --text 'Racecar' --exact
python3 solution.py --file phrase.txt --keep-accents
```

Options:

- `--text TEXT` — check a literal string.
- `--file PATH` — read text from a UTF-8 file.
- `--exact` — compare raw characters, disabling all normalisation.
- `--case-sensitive` — keep letter case (punctuation/whitespace still ignored).
- `--keep-accents` — do not strip combining accents.
- `--encoding NAME` — file encoding, default UTF-8.
- `--demo` — scripted demonstration with no input.

The program exits 0 when a check completes, whether or not the text is a palindrome; it exits 1 only for input errors. This makes the output easy to script around without treating "not a palindrome" as a crash.

## Example Output

```text
$ python3 solution.py --demo
Palindrome checks (case, punctuation, whitespace, accents ignored):

Input:  'racecar'
Result: YES — palindrome
Normalized: 'racecar' (7 characters)

Input:  'A man, a plan, a canal: Panama'
Result: YES — palindrome
Normalized: 'amanaplanacanalpanama' (21 characters)

Input:  "No 'x' in Nixon"
Result: YES — palindrome
Normalized: 'noxinnixon' (10 characters)

Input:  'La mariée ira mal'
Result: YES — palindrome
Normalized: 'lamarieeiramal' (14 characters)

Input:  'Hello, world!'
Result: NO — not a palindrome
Normalized: 'helloworld' (10 characters)
First mismatch at position 0: 'h' vs 'd'

With --exact (raw comparison):
Input:  'Racecar'
Result: NO — not a palindrome
Normalized: 'Racecar' (7 characters)
First mismatch at position 0: 'R' vs 'r'
```

## Implementation Notes

Normalisation applies NFKD, removes characters whose Unicode category is a combining mark, case-folds with `str.casefold()`, then keeps only alphanumeric characters. The comparison builds the reversed string (`O(n)` time and space) and scans the first half to locate the first mismatch; `right` is read from the reversed string, which makes the reported pair directly comparable. Empty or punctuation-only input normalises to an empty string and is reported as a palindrome by definition. Accent folding is language-agnostic, so `é` and `e` are treated as equivalent; use `--keep-accents` when that distinction matters.
