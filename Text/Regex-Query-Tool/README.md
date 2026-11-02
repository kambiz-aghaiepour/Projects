# Regex Query Tool

*Category: Text · Project directory: `Text/Regex-Query-Tool/`*

## Problem

A tool that allows the user to enter a text string and then in a separate control enter a regex pattern. It will run the regular expression against the source text and return any matches or flag errors in the regular expression.

## Features

- Compiles arbitrary Python regular expressions against text from `--text`, `--file`, or stdin.
- Shows every match with its character span, numbered capture groups, named groups, and a context line with the match bracketed.
- Reports invalid patterns with the parser's message and character position instead of a traceback.
- Optional `--replace` using Python's `re.sub` syntax (`\1`, `\g<name>`), with a substitution count.
- Flags for case-insensitive (`-i`), multiline (`-m`), and dot-all (`-s`) matching.
- `--json` for structured output.
- Interactive prompt mode when run on a terminal with no pattern.
- `--demo` runs named-group, timestamp, replacement, invalid-pattern, and no-match examples.

## Requirements

Python 3.10+ (standard library only: `re`, `json`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py '\d+' --text 'order 42, item 7'
python3 solution.py '(?P<user>\w+)@(?P<domain>[\w.-]+)' --file access.log
python3 solution.py '\bERROR\b' --file app.log -i
python3 solution.py '(\w+)@(\w+)' --text 'ada@example' --replace '\2 at \1'
python3 solution.py '\d{4}-\d{2}-\d{2}' --file notes.txt --json
```

| Option | Meaning |
| --- | --- |
| `pattern` | Regular expression; omit for interactive mode. |
| `--text TEXT` | Source text on the command line. |
| `--file PATH` | Read source text from a file instead. |
| `-i`, `--ignore-case` | Case-insensitive matching. |
| `-m`, `--multiline` | `^`/`$` match at line boundaries. |
| `-s`, `--dotall` | `.` matches newlines. |
| `--replace TEMPLATE` | Replace matches and print the result. |
| `--json` | Emit a JSON object with matches, spans, groups, and replacement. |
| `--demo` | Run the scripted demonstration. |

If neither `--text` nor `--file` is given, text is read from stdin.

## Example Output

```text
Pattern: (?P<level>INFO|WARN|ERROR)\s+user=(?P<user>\w+)\s+email=(?P<email>[\w.-]+@[\w.-]+)
Flags:   none
Matches: 4 in 259 character(s)

[1] 'INFO  user=ada email=ada@example.com'  span=(20, 56)
    groups: 1='INFO', 2='ada', 3='ada@example.com'
    named:  level='INFO', user='ada', email='ada@example.com'
    line:   2024-05-01 12:00:01 [INFO  user=ada email=ada@example.com] id=42

[2] 'WARN  user=grace email=grace@example.org'  span=(83, 123)
    groups: 1='WARN', 2='grace', 3='grace@example.org'
    named:  level='WARN', user='grace', email='grace@example.org'
    line:   2024-05-01 12:00:05 [WARN  user=grace email=grace@example.org] id=7
```

Replacement example:

```text
Pattern: (?P<user>[\w.+-]+)@(?P<domain>[\w.-]+)
Substitutions: 4
2024-05-01 12:00:01 INFO  user=ada email=ada [at] example.com id=42
```

Invalid patterns are reported like this and exit with status 2:

```text
error: invalid regular expression: unterminated character set at position 1
```

## Implementation Notes

- Patterns use Python's `re` syntax, including lookarounds, inline flags, named groups, and backreferences.
- `re.finditer` yields non-overlapping matches. Span offsets are character offsets in the source string (not byte offsets), and a zero-width match has `start == end`.
- Group values that did not participate in the match are shown as `None`; named groups come from `rx.groupindex`.
- Context is computed from the line containing the match start, with the matched text wrapped in `[ ]`; long prefixes/suffixes are truncated with `…`.
- Replacement delegates to `rx.subn`, so backreference syntax and errors are Python's. An invalid replacement is reported as an error and exits 2.
- There is no regex execution timeout: a catastrophic-backtracking pattern can run for a long time. Use bounded, trusted patterns for untrusted input.
