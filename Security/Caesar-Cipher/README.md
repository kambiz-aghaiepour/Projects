# Caesar Cipher

**Category:** `Security` · **Project:** `Caesar-Cipher`

## Problem

> Implement a Caesar cipher, both encoding and decoding. The key is an integer
> from 1 to 25. This cipher rotates the letters of the alphabet (A to Z). The
> encoding replaces each letter with the 1st to 25th next letter in the
> alphabet (wrapping Z to A). This simple monoalphabetic substitution cipher
> provides almost no security.

## Features

- `encode` and `decode` with a key validated to the range 1–25.
- Preserves letter case and leaves spaces, punctuation, digits, and non-ASCII
  characters unchanged.
- `brute` prints the ciphertext decoded under all 25 keys and marks the most
  plausible English plaintext.
- `analyze` provides frequency-analysis assistance: letter counts and
  percentages, the classic "most common letter probably stands for E" key
  estimate, and the top three candidate keys ranked by chi-squared distance
  from English letter frequencies, with sample decodings.
- Interactive menu when run with no arguments.
- `--demo` exercises every feature, including the required examples
  `HI` + key 2 → `JK` and `HI` + key 20 → `BC`, without reading any input.

## Requirements

Python 3.10+ and the standard library only (`argparse`, `collections`, `re`,
`string`). No installation step is needed.

## Usage

```bash
python3 solution.py --demo
python3 solution.py encode "Hello, World!" -k 3
python3 solution.py decode "Khoor, Zruog!" -k 3
python3 solution.py brute "Wkh txlfn eurzq ira"
python3 solution.py analyze "Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj"
python3 solution.py                       # interactive menu
echo "KHOOR" | python3 solution.py decode - -k 3
```

Options and behavior:

- `encode TEXT -k KEY` — encrypt `TEXT` with `KEY` (1–25).
- `decode TEXT -k KEY` — decrypt `TEXT` with `KEY` (1–25).
- `brute TEXT` — show all 25 possible decodings; the best-scoring one is
  marked `<-- best guess`.
- `analyze TEXT` — print the frequency report and likely keys.
- The text argument may be omitted (or given as `-`) to read from standard
  input; on a terminal the program prompts for it instead.
- `--demo` — run the scripted demonstration and exit.
- `-h/--help` — show usage.

An invalid key prints a clear error and exits with status 2. The library
functions validate keys too, so `encode(text, 0)` raises `ValueError` rather
than silently doing nothing.

## Example Output

Trimmed from `python3 solution.py --demo`:

```
Caesar Cipher demo
==============================================================
Known examples from the problem statement:
  encode('HI',  2) = 'JK'
  decode('JK',  2) = 'HI'
  encode('HI', 20) = 'BC'

Round trips for 'Attack at Dawn, 06:30!':
  key  3: Dwwdfn dw Gdzq, 06:30!
          back: Attack at Dawn, 06:30!  (match: True)
  key 13: Nggnpx ng Qnja, 06:30!
          back: Attack at Dawn, 06:30!  (match: True)

Brute force of 'Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj' (encrypted with key 3):
All 25 keys for: Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj
   1: Vjg swkem dtqyp hqz lworu qxgt vjg ncba fqi
   2: Uif rvjdl cspxo gpy kvnqt pwfs uif mbaz eph
   3: The quick brown fox jumps over the lazy dog  <-- best guess
   4: Sgd pthbj aqnvm enw itlor nudq sgd kzyx cnf
  ...

Frequency analysis of a longer ciphertext (true key 7):
  ciphertext: Pa dhz aol ilza vm aptlz, pa dhz aol dvyza vm aptlz, pa dhz...
Letters analysed: 260
Most common letters:
  l    35   13.5%
  a    29   11.2%
  z    28   10.8%
  ...
English reference order: e t a o i n s h r d l u
Most common letter 'l' implies key 7 if it stands for 'e'
Best keys by chi-squared fit (lower is better):
  key  7  score    24.30  It was the best of times, it was the worst of times, it was...
  key 19  score   625.72  Wh kog hvs psgh ct hwasg, wh kog hvs kcfgh ct hwasg, wh kog...
  key 23  score   940.86  Sd gkc dro locd yp dswoc, sd gkc dro gybcd yp dswoc, sd kog...
  best key detected: 7 (expected 7)

Demo complete.
```

## Implementation Notes

- **Shifting:** each character is inspected with `ord`; only `A–Z` and `a–z`
  are rotated, so case is retained and everything else is copied verbatim.
  Decoding is the same routine with `-key` (equivalently `26 - key`).
- **Brute force:** 25 decodings and a plausibility score each, O(25·n). The
  output is printed in key order for readability while the best guess is
  marked from the ranked list.
- **Scoring:** chi-squared distance between the candidate's letter counts and
  standard English frequencies, minus 3 points per occurrence of a common
  English word. The word bonus stabilizes rankings on short inputs, where
  letter-frequency statistics alone are noisy. Lower is better.
- **Frequency analysis:** the report shows the observed distribution, the naive
  estimate `key = (most_common_letter - 'e') mod 26`, and the three best keys
  by score. It is decision support, not a guaranteed break.
- **Limitations:** analysis needs a reasonable amount of English text —
  roughly 100+ letters — and is unreliable for very short messages, proper
  nouns, or other languages. The cipher itself has only 25 keys and offers no
  real security; it is a teaching and puzzle tool.
