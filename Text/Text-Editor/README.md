# Text Editor

*Category: Text · Project directory: `Text/Text-Editor/`*

## Problem

Notepad style application that can open, edit, and save text documents. Optional: Add syntax highlighting and other features.

This implementation is a terminal line editor rather than a GUI: `tkinter` is not available in every environment, so the same editing operations are exposed as commands and as an optional curses full-screen mode.

## Features

- Load, view, edit, and save UTF-8 text files.
- Numbered line view with optional ranges (`view 3-8`).
- Insert before a line, append at the end, delete one line or a range, replace a line.
- Case-insensitive substring search with line numbers.
- Undo stack (last 100 buffer states).
- Dirty-state tracking and `save` to the current or a new path.
- Optional curses TUI: arrow keys, typing, Enter, Backspace, `Ctrl-S` to save, `Ctrl-Q` to quit.
- Scripted `--demo` that edits a temporary file and verifies the result.

## Requirements

Python 3.10+ (standard library only; curses is part of the standard library on Unix).

## Usage

```bash
python3 solution.py --demo
python3 solution.py notes.txt
python3 solution.py notes.txt --tui
```

With a file argument the editor opens it and enters the `editor>` prompt. With no file it starts with an empty buffer. `--tui` opens the curses interface instead of the command prompt and needs a real terminal.

### Commands

| Command | Meaning |
| --- | --- |
| `open <path>` | Load a file (replaces the buffer). |
| `view [start[-end]]` | Show all lines or a 1-based range. |
| `insert <line> <text>` | Insert text before `<line>`; `len+1` appends. |
| `append <text>` | Add a line at the end. |
| `delete <line>` / `delete <start-end>` | Delete one line or an inclusive range. |
| `replace <line> <text>` | Replace a whole line. |
| `find <text>` | Case-insensitive substring search. |
| `undo` | Restore the previous buffer. |
| `save [path]` | Write the buffer, optionally to a new path. |
| `lines` | Show the line count and whether the buffer is modified. |
| `help`, `quit` | Show commands or leave. |

Text after the line number is taken literally, so runs of spaces are preserved. `open` and `save` accept quoted paths.

## Example Output

```text
Text Editor demo
================

editor> open notes.txt
Opened notes.txt (5 lines).

editor> view
1 | Shopping list
2 | milk
3 | eggs
4 | bread
5 | call the plumber

editor> replace 2 oat milk
Replaced line 2.

editor> insert 5 a new line before the plumber
Inserted before line 5.

editor> delete 3
Deleted 1 line(s).

editor> append buy stamps
Appended line 6.

editor> find milk
2: oat milk

editor> save edited.txt
Saved 6 lines to edited.txt.

--- saved file ---
Shopping list
oat milk
bread
a new line before the plumber
call the plumber
buy stamps
demo assertion passed: file contents match the scripted edits
```

## Implementation Notes

- The buffer is a `list[str]`; edits are O(n) because lines shift, which is fine for ordinary documents. Undo snapshots the whole list, capped at 100 entries.
- Commands are tokenized with `shlex` for verbs and paths; text commands use a regex on the raw command so internal spacing survives.
- Files are read and written as UTF-8 with a trailing newline. Saves are direct writes, not atomic renames.
- The curses mode is intentionally minimal: printable ASCII input only, no syntax highlighting, no search dialog. It exists as an optional convenience over the scriptable command mode.
- Ctrl-C or EOF at the interactive prompt exits without forcing a save; unsaved changes are reported on `quit`.
