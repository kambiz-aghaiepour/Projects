# Pig Latin

*Category: **Text** · Project directory: `Text/Pig-Latin`*

## Problem

Pig Latin is a game of alterations played on the English language. To create the Pig Latin form of an English word the initial consonant sound is transposed to the end of the word and an ay is affixed (Ex.: "banana" would yield anana-bay).

This implementation applies the standard rules to whole sentences while leaving punctuation, spacing, digits, and capitalisation readable.

## Features

- Vowel-initial words take `-way`: `apple → appleway`.
- Initial consonant clusters move to the end with `-ay`: `string → ingstray`, `school → oolschay`.
- `qu` is treated as one consonant unit: `quick → ickquay`.
- `y` rules: consonantal at the start of a syllable (`yellow → ellowyay`) and vocalic after a consonant (`rhythm → ythmrhay`); vowel-less words simply take `-ay` (`nth → nthay`).
- Punctuation and spacing are preserved exactly; numbers are untouched.
- Title case and ALL CAPS are preserved; apostrophes stay inside words and hyphens separate independently translated words.
- Input from `--text`, a UTF-8 file, piped stdin, or an interactive prompt.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --text 'banana split'
python3 solution.py --text "Hello, world! The quick brown fox doesn't jump."
echo 'Well-known tools.' | python3 solution.py
python3 solution.py --file notes.txt
```

Options:

- `--text TEXT` — translate a literal string.
- `--file PATH` — read text from a UTF-8 file.
- `--encoding NAME` — file encoding, default UTF-8.
- `--demo` — scripted demonstration with no input.

## Example Output

```text
$ python3 solution.py --demo
Word translations:
  banana -> ananabay
  apple  -> appleway
  string -> ingstray
  school -> oolschay
  quick  -> ickquay
  yellow -> ellowyay
  rhythm -> ythmrhay
  nth    -> nthay
  Hello  -> Ellohay
  HELLO  -> ELLOHAY
  don't  -> on'tday

Sentence:
  Hello, world! The quick brown fox doesn't jump over 3 lazy dogs.
  Ellohay, orldway! Ethay ickquay ownbray oxfay oesn'tday umpjay overway 3 azylay ogsday.

Hyphenated text:
  Well-known state-of-the-art tools.
  Ellway-ownknay atestay-ofway-ethay-artway oolstay.
```

## Implementation Notes

A single regex, `[A-Za-z]+(?:['’][A-Za-z]+)*`, finds English word tokens and a callback replaces each one, so every non-word character is emitted untouched. `first_vowel_index` scans the onset, skipping `qu` as a pair and treating `y` as a vowel only when it follows a consonant. Translation is O(n) in the input length. Capitalisation is reconstructed heuristically: all-uppercase words stay uppercase, a leading capital is reapplied, and other mixed-case spellings (e.g. `iPhone`) are lowercased apart from the first letter. This is a one-way encoder; decoding Pig Latin is ambiguous because different source words can map to the same output.
