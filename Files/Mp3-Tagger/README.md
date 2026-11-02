# Mp3 Tagger

Category: `Files` · Project: `Mp3-Tagger`

## Problem

Modify and add ID3v1 tags to MP3 files. See if you can also add the album art
into the MP3 file's header as well as other ID3v2 tags.

## Features

- Read ID3v1 and ID3v2.3/ID3v2.4 tags, with v2 taking precedence over v1.
- Write title, artist, album, year, genre, track and comment.
- Choose `--tag-version 2.3` (UTF-16 text frames) or `2.4` (UTF-8, syncsafe frames).
- Embed album art as an `APIC` front-cover frame (`PNG`, `JPEG`, `GIF`, `WEBP`).
- Extract embedded art back to a file; remove art without touching other fields.
- `--v1-only` strips ID3v2 and writes only a 128-byte ID3v1 trailer; `--no-v1`
  keeps ID3v2 only.
- Preserves unknown ID3v2 frames and never re-encodes the audio payload.
- Atomic writes via a temporary file in the same directory plus `os.replace`,
  preserving file permissions.
- `--demo` builds a dummy MP3 and a valid PNG, then round-trips both tag
  versions and the v1 fallback.

## Requirements

Python 3.10+ and the standard library only. Works with any file that contains
an MPEG audio payload; real MP3s are not required for the demo.

## Usage

```bash
# Show every tag
python3 solution.py song.mp3

# Set fields (repeatable), writing ID3v2.3 + ID3v1
python3 solution.py song.mp3 --set title="Night Drive" --set artist="The Cars" \
    --set album="Heartbeat City" --set year=1984 --set genre=Rock --set track=3/10

# Embed a cover and write ID3v2.4
python3 solution.py song.mp3 --art cover.png --tag-version 2.4

# Extract the cover
python3 solution.py song.mp3 --extract-art cover-out.png

# Remove all tags
python3 solution.py song.mp3 --clear

# Write only an ID3v1 trailer (no album art)
python3 solution.py song.mp3 --v1-only --set title="Legacy Player"

# Scripted demonstration
python3 solution.py --demo
```

Options:

| Option | Meaning |
| --- | --- |
| `file` | MP3 file to inspect or edit |
| `--show` | Print tags (default when no edit option is given) |
| `--set FIELD=VALUE` | Set `title`, `artist`, `album`, `year`, `genre`, `track`, `comment`; empty clears |
| `--art PATH` | Embed this image as the front cover |
| `--extract-art PATH` | Write embedded art to a file and exit |
| `--remove-art` | Drop embedded art |
| `--clear` | Remove all tags (both ID3v1 and ID3v2) |
| `--tag-version {2.3,2.4}` | ID3v2 version to write (default 2.3) |
| `--no-v1` | Do not write an ID3v1 trailer |
| `--v1-only` | Strip ID3v2; write only ID3v1 |
| `--demo` | Run the offline demonstration |

### Field to frame mapping

| Field | ID3v2 frame | ID3v1 offset |
| --- | --- | --- |
| title | `TIT2` | bytes 3–32 |
| artist | `TPE1` | bytes 33–62 |
| album | `TALB` | bytes 63–92 |
| year | `TYER` (2.3) / `TDRC` (2.4) | bytes 93–96 |
| comment | `COMM` (language `eng`) | bytes 97–126 |
| track | `TRCK` | byte 126 (ID3v1.1) |
| genre | `TCON` | byte 127 (genre index) |
| cover | `APIC` (picture type 3) | not supported |

## Example Output

```
Built dummy MP3 (3336 bytes) and PNG cover (165 bytes)
Wrote ID3v2.3 + ID3v1; file is now 5002 bytes
ID3v2.3 round-trip: title='Demo Track (Remastered)', artist='The Standard Library', album='Batteries Included', year='2026', track='7/12'
Album art: image/png, 165 bytes, PNG signature=b'\x89PNG\r\n\x1a\n'
File starts with b'ID3\x03\x00\x00' (ID3v2.3, no flags)
ID3v2.4 rewrite preserved the audio payload byte-for-byte.
ID3v1-only fallback reads: title='Demo Track (Remastered)', track='7', genre='Electronic'
Extracted art verified as PNG: extracted.png
Atomic write left no temporary files behind.

Demo complete: tags and album art round-trip correctly.
```

## Implementation Notes

- **ID3v1:** exactly 128 bytes at the end of the file: `TAG` + 30-byte title,
  30-byte artist, 30-byte album, 4-byte year, 28-byte comment + NUL + track
  byte + genre byte. Strings are Latin-1, NUL/space padded; anything outside
  Latin-1 becomes `?`.
- **ID3v2:** the 10-byte header stores a 28-bit syncsafe body size. ID3v2.3
  frames use plain 32-bit big-endian sizes; ID3v2.4 frames use syncsafe sizes.
  Text frames begin with an encoding byte (Latin-1, UTF-16 with BOM, UTF-16BE,
  or UTF-8) and `COMM`/`APIC` use NUL-terminated strings in that encoding.
  Tag-level unsynchronisation and extended headers are handled on read.
- **Round-tripping:** the existing v2 tag(s) and v1 trailer are stripped, the
  audio bytes are kept verbatim, and the new tags are wrapped around them. The
  demo asserts the audio payload is byte-identical after both rewrites.
- **Atomicity:** output goes to a `mkstemp` file in the same directory, is
  fsynced, gets the original mode, and replaces the original in one `os.replace`.
- **Limitations:** ID3v2.2 is rejected (only 2.3/2.4 are in scope); compressed
  or encrypted frames are skipped on read; writing does not unsynchronise or
  encrypt; APIC is written as a Latin-1-described front cover; ID3v1 cannot
  store art and truncates long fields; the program does not validate MPEG audio
  frames, so any binary payload after the tag is preserved but not played.
