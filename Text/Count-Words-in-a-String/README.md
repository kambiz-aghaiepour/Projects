# Count Words in a String

*Category: **Text** · Project directory: `Text/Count-Words-in-a-String`*

## Problem

Counts the number of individual words in a string. For added complexity read these strings in from a text file and generate a summary.

This implementation accepts a literal string, piped stdin, or any number of files, and reports line, word, and uniqueness statistics plus the most common words.

## Features

- Three input modes: `--text`, one or more files (with `-` for stdin), or piped/interactive stdin.
- Per-source summary: characters, lines, words, unique words, average word length, longest word.
- Top-N word frequencies with percentages (`--top`, default 5).
- Multiple files are shown in a per-file table and merged into an overall summary.
- Case-insensitive uniqueness by default; `--case-sensitive` distinguishes `The` from `the`.
- `--json` for machine-readable output covering every source and the summary.
- Graceful error (message + exit 1) for missing or undecodable files.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --text 'one two two three'
python3 solution.py poem.txt
python3 solution.py poem.txt notes.txt --top 10
cat notes.txt | python3 solution.py
python3 solution.py - --json < notes.txt
```

Options:

- `FILE ...` — files to analyse; `-` reads standard input. With no files the program reads piped stdin or prompts interactively.
- `--text TEXT` — analyse a literal string (cannot be combined with files).
- `--top N` — number of top words to display, minimum 1, default 5.
- `--case-sensitive` — count `The` and `the` as separate words.
- `--json` — emit per-source and combined statistics as JSON.
- `--encoding NAME` — file encoding, default UTF-8.
- `--demo` — scripted demonstration using an inline string and two temporary files.

## Example Output

```text
$ python3 solution.py --demo
String input:
Source: <text>
Characters: 74  |  Lines: 1  |  Words: 15  |  Unique words: 10
Average word length: 3.8  |  Longest word: 'sleeps'

Top 5 word(s):
   1. the                   4  (26.7%)
   2. fox                   2  (13.3%)
   3. dog                   2  (13.3%)
   4. quick                 1  ( 6.7%)
   5. brown                 1  ( 6.7%)

Multiple files:
File                      Lines  Words  Unique
----------------------------------------------
poem.txt                      2     15      10
notes.txt                     2     11       9

Combined summary:
Source: all sources
Characters: 135  |  Lines: 4  |  Words: 26  |  Unique words: 15
Average word length: 4.0  |  Longest word: 'sleeps'

Top 5 word(s):
   1. the                   5  (19.2%)
   2. quick                 3  (11.5%)
   3. dog                   3  (11.5%)
   4. fox                   2  ( 7.7%)
   5. lazy                  2  ( 7.7%)
```

The demo ends with a JSON excerpt, omitted here for brevity.

## Implementation Notes

Words are matched with the Unicode-aware regex `[^\W_]+(?:['’][^\W_]+)*`, which accepts letters and digits, keeps internal apostrophes (`don't` is one word), and excludes underscores. Hyphens split words (`well-known` counts as two). Lines are physical lines: newline count plus one for a final unterminated line. Frequencies use `Counter`; without `--case-sensitive`, keys are passed through `str.casefold()`. Multi-file aggregation merges the full frequency counters rather than the displayed top-N lists, so a word that is frequent overall appears correctly even if it was outside an individual file's top N. Complexity is O(total characters + words) plus the cost of selecting the top N words; memory is O(unique words).
