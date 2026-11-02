# Alarm Clock

**Category:** Numbers · **Project:** `Alarm-Clock`

## Problem

> A simple clock where it plays a sound after X number of minutes/seconds or at a particular time.

## Features

- Relative alarms: `90s`, `10m`, `1h30m`, `1:30` (mm:ss), or a bare number of minutes.
- Absolute alarms: `07:30`, `19:45:10`, or `7:30pm`; a time already past today rolls over to tomorrow.
- Live countdown for waits longer than a second, with the target time shown when the alarm is set.
- Firing signal is a terminal bell or a printed ASCII "beep" pattern — no audio files or libraries.
- Custom message and `--sound {beep,bell,none}` selection.
- Interactive prompts when no alarm option is supplied; `Ctrl-C` cancels without a traceback.
- `--demo` schedules a 0.3-second alarm, so verification never sleeps for minutes.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --in 90s --message "Tea is ready"
python3 solution.py --in 1h30m
python3 solution.py --at 07:30
python3 solution.py --at 7:30pm --sound bell
```

- `-i/--in DURATION` — relative delay; supports `h`, `m`, `s` units and `hh:mm[:ss]`.
- `-a/--at TIME` — wall-clock time; use `--at` instead of `--in`.
- `-m/--message TEXT` — text announced when the alarm fires.
- `--sound {beep,bell,none}` — output style (default `beep`).
- `--demo` — scripted 0.3-second demonstration; exits 0 without user input.
- With no arguments, the program prompts for a duration and message.

## Example Output

```text
Alarm Clock demo
----------------------------------------
Parsed durations:
  '90s'        -> 1m 30s
  '1h30m'      -> 1h 30m 00s
  '1:30'       -> 1m 30s
  '0.5'        -> 30s
  '2 minutes'  -> 2m 00s

Wall-clock alarm: 07:30 seen at 2026-01-01 22:15 rings at 2026-01-02 07:30

Ringing a 0.3-second demo alarm...

[alarm] Demo alarm: stand up and stretch

        .----------------.
        |  )  BEEP  BEEP |
        '----------------'
             \   (  )
              \__) )

[alarm] done
```

## Implementation Notes

The countdown uses `time.monotonic()` so system clock adjustments cannot make it
drift or fire early; the wall-clock target for `--at` is calculated once with
`datetime` and converted to a delay. The "sound" is intentionally terminal-only:
a bell character plus a printable pattern, which works over SSH and in CI.
Real audio playback would need a platform-specific player and is out of scope.
Sub-second waits skip the countdown line so `--demo` output stays clean.
