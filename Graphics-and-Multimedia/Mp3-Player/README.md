# Mp3 Player

**Category:** Graphics-and-Multimedia · **Project:** Mp3-Player

## Problem

> A simple program for playing your favorite music files. Add features you
> think are missing from your favorite music player.

## Features

- **Playlist management** in a JSON file: add files or scan folders, list the
  playlist, reload it on the next run.
- **Metadata** from ID3v2.3/2.4 text frames (title, artist, album), with a
  fallback that parses `Artist - Title` from the filename.
- **Duration detection** without third-party libraries: WAV headers and a full
  MPEG frame walk for MP3 (handles CBR, VBR and ID3 padding).
- **Transport controls**: play, pause, resume, next, previous, seek, stop and
  simulated time advance, available both in an interactive shell and through
  the demo.
- **Shuffle and repeat** modes (`off`, `one`, `all`), with a deterministic
  shuffle seed available for scripting/tests.
- **Real playback** through `ffplay`, `mpg123` or `aplay` when one is installed
  and `--play` is passed. Without an installed player, every control still
  works in simulation mode — no sound card required.
- Handles empty playlists, missing files and unsupported formats with clear
  messages.

## Requirements

Python 3.10+ and the standard library only. Optional external players: `ffplay`
(part of ffmpeg), `mpg123`, or `aplay` (ALSA, WAV only). `ffmpeg` is also used
by the demo to produce one tagged MP3 when available.

## Usage

```bash
# Scripted demo: generates silent WAVs and a tagged MP3, then simulates controls
python3 solution.py --demo

# Build a playlist by scanning folders
python3 solution.py --add ~/Music/albums --list

# Interactive shell (list / play N / pause / next / shuffle on / repeat all)
python3 solution.py

# Real playback through the detected audio backend
python3 solution.py --play --shuffle --repeat all

# Start from a specific track
python3 solution.py --play --track 3
```

| Option | Meaning |
| --- | --- |
| `--playlist FILE` | JSON playlist to load/save (default `playlist.json`) |
| `--add PATH...` | Add audio files or recursively scan directories |
| `--list` | Print the numbered playlist and exit |
| `--play` | Play audio for real with `ffplay`/`mpg123`/`aplay` |
| `--track N` | Start at track N with `--play` |
| `--shuffle` | Shuffle order |
| `--repeat {off,one,all}` | Repeat mode (default `off`) |
| `--demo` | Generate audio and run a scripted session |

Interactive shell commands: `list`, `play N`, `pause`, `resume`, `next`,
`prev`, `seek SEC`, `tick SEC`, `shuffle on|off`, `repeat off|one|all`,
`status`, `save`, `quit`.

## Example Output

```text
Mp3 Player demo
  generated: 3 WAV + 1 MP3 with ID3 tags (32.2 KiB)
  playlist:
    1. Neon Skyline — Night Drive  (0:04.0)
    2. Neon Skyline — Static Bloom  (0:06.0)
    3. Paper Satellites — Slow Orbit  (0:03.0)
    4. Neon Skyline — Afterglow  [Midnight Transit]  (0:04.1)
  audio backend detected: ffplay
  play 1  -> [playing] 1/4  Neon Skyline — Night Drive  0:00.0/0:04.0  shuffle=off repeat=off
  +1.5s   -> [playing] 1/4  Neon Skyline — Night Drive  0:01.5/0:04.0  shuffle=off repeat=off
  pause   -> [paused ] 1/4  Neon Skyline — Night Drive  0:01.5/0:04.0  shuffle=off repeat=off
  resume  -> [playing] 1/4  Neon Skyline — Night Drive  0:03.0/0:04.0  shuffle=off repeat=off
  next    -> True; [playing] 2/4  Neon Skyline — Static Bloom  0:00.0/0:06.0  shuffle=off repeat=off
  prev    -> [playing] 1/4  Neon Skyline — Night Drive  0:00.0/0:04.0  shuffle=off repeat=off
  shuffle -> order=[4, 2, 1, 3]
  repeat one, +5s -> [playing] 3/4  Paper Satellites — Slow Orbit  0:00.0/0:03.0  shuffle=off repeat=one
  repeat all, +4.5s -> [playing] 1/4  Neon Skyline — Night Drive  0:00.3/0:04.0  shuffle=off repeat=all
  saved playlist: playlist.json -> 4 tracks reloaded
  checks  : 5/5 passed
Demo complete (simulated transport: no audio device required).
```

## Implementation Notes

- `read_id3()` reads the 10-byte ID3v2 header, decodes the syncsafe tag size,
  handles unsynchronisation and extended headers, then walks 10-byte frame
  headers. Text encodings 0–3 (Latin-1, UTF-16, UTF-16BE, UTF-8) are supported;
  unknown frames such as `APIC` are skipped.
- `mp3_duration()` walks MPEG audio frame headers using the version/layer
  bitrate and sample-rate tables. It counts 1152 samples for MPEG-1 Layer III
  and 576 for MPEG-2/2.5 Layer III, giving accurate durations for VBR files
  without parsing a Xing header.
- The player is a pure state machine: `tick(seconds)` advances position and
  handles end-of-track, repeat-one restart, repeat-all wrap and stop at the end.
  This makes the demo deterministic and lets it run in milliseconds.
- Real playback is best-effort. `ffplay` supports starting at an offset
  (`-ss`); `mpg123` and `aplay` restart the file from the beginning on resume.
  Playback runs as a subprocess and is terminated when the player stops.
- Limitations: ID3v2.2 tags (three-character frame IDs) are not parsed, cover
  art/lyrics are ignored, and formats other than WAV/MP3 report `0:00.0`
  duration unless their container is supported by the external player.
