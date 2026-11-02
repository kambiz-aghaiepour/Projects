#!/usr/bin/env python3
"""A small command-line alarm clock.

Schedule an alarm after a delay (``--in 10m``) or at a wall-clock time
(``--at 07:30``).  When it fires the program prints a message, rings the
terminal bell and shows a short ASCII "beep" pattern.  No audio library or
sound file is required.

Examples:
    python3 solution.py --in 90s --message "Tea is ready"
    python3 solution.py --at 07:30
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as TimeOfDay, timedelta

_DURATION_TOKEN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)(?P<unit>hours?|hrs?|h|minutes?|mins?|m|"
    r"seconds?|secs?|s)",
    re.IGNORECASE,
)

_CLOCK_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M:%S%p", "%I:%M%p", "%I%p")

_BEEP_PATTERN = r"""
        .----------------.
        |  )  BEEP  BEEP |
        '----------------'
             \   (  )
              \__) )
"""


@dataclass(frozen=True)
class Alarm:
    """A scheduled alarm: either a delay or an absolute wall-clock time."""

    label: str
    seconds: float
    target: datetime | None = None


def parse_duration(text: str) -> float:
    """Convert a human duration (``90s``, ``1h30m``, ``1:30``) to seconds.

    A bare number is interpreted as minutes, matching the original problem's
    "after X minutes" wording.
    """

    raw = text.strip().lower()
    if not raw:
        raise ValueError("duration is empty")

    if ":" in raw:
        parts = raw.split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"invalid duration {text!r}; use hh:mm[:ss]")
        try:
            numbers = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError(f"invalid duration {text!r}") from exc
        if any(number < 0 for number in numbers):
            raise ValueError("duration cannot be negative")
        if len(numbers) == 2:
            total = numbers[0] * 60 + numbers[1]
        else:
            total = numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
        if total <= 0:
            raise ValueError("duration must be greater than zero")
        return total

    compact = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"\d+(?:\.\d+)?", compact):
        minutes = float(compact)
        if minutes <= 0:
            raise ValueError("duration must be greater than zero")
        return minutes * 60

    total = 0.0
    position = 0
    for match in _DURATION_TOKEN.finditer(compact):
        if match.start() != position:
            raise ValueError(f"could not parse {compact[position:match.start()]!r}")
        value = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("h"):
            total += value * 3600
        elif unit.startswith("m"):
            total += value * 60
        else:
            total += value
        position = match.end()
    if position != len(compact) or total <= 0:
        raise ValueError(f"could not parse duration {text!r}")
    return total


def parse_clock_time(text: str) -> TimeOfDay:
    """Parse ``07:30``, ``7:30pm`` or ``19:45:10`` into a time of day."""

    cleaned = re.sub(r"\s+", "", text).upper()
    for fmt in _CLOCK_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"invalid time {text!r}; try HH:MM or 7:30pm")


def next_occurrence(clock_time: TimeOfDay, now: datetime) -> datetime:
    """Return the next datetime at ``clock_time`` strictly after ``now``."""

    target = now.replace(
        hour=clock_time.hour,
        minute=clock_time.minute,
        second=clock_time.second,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return target


def format_seconds(seconds: float) -> str:
    """Format a duration as ``1h 02m 03s`` (sub-second values keep decimals)."""

    seconds = max(0.0, seconds)
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    if seconds < 10 and seconds != int(seconds):
        return f"{seconds:.1f}s"
    return f"{secs}s"


def sound_the_alarm(sound: str, message: str, pause: float = 0.25) -> None:
    """Print the alarm message plus a terminal bell or ASCII beep pattern."""

    print(f"\n[alarm] {message}")
    if sound == "bell":
        for _ in range(3):
            print("\a", end="", flush=True)
            time.sleep(pause)
        print()
    elif sound == "beep":
        print(_BEEP_PATTERN)
        if pause:
            time.sleep(pause)
    print("[alarm] done")


def wait_for_alarm(alarm: Alarm, sound: str) -> None:
    """Block until the alarm fires, showing a countdown for longer waits."""

    if alarm.seconds > 1.0:
        end = time.monotonic() + alarm.seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            print(
                f"\r[alarm] {alarm.label}: {format_seconds(remaining)} remaining ",
                end="",
                flush=True,
            )
            time.sleep(min(0.5, remaining))
        print("\r" + " " * 60 + "\r", end="")
    else:
        time.sleep(alarm.seconds)
    sound_the_alarm(sound, alarm.label, pause=0.2 if sound == "bell" else 0.0)


def build_alarm(args: argparse.Namespace) -> Alarm:
    """Turn parsed command-line options into an :class:`Alarm`."""

    if args.at:
        clock_time = parse_clock_time(args.at)
        now = datetime.now()
        target = next_occurrence(clock_time, now)
        seconds = (target - now).total_seconds()
        label = args.message or f"Alarm for {clock_time.strftime('%H:%M')}"
        return Alarm(label=label, seconds=max(0.0, seconds), target=target)

    seconds = parse_duration(args.delay or "")
    return Alarm(label=args.message or "Wake up!", seconds=seconds)


def run_demo() -> int:
    """Scripted demonstration; sleeps for only a fraction of a second."""

    print("Alarm Clock demo")
    print("-" * 40)
    examples = ["90s", "1h30m", "1:30", "0.5", "2 minutes"]
    print("Parsed durations:")
    for text in examples:
        print(f"  {text!r:12} -> {format_seconds(parse_duration(text))}")

    reference = datetime(2026, 1, 1, 22, 15, 0)
    clock_time = parse_clock_time("07:30")
    target = next_occurrence(clock_time, reference)
    print(
        f"\nWall-clock alarm: 07:30 seen at {reference:%Y-%m-%d %H:%M} "
        f"rings at {target:%Y-%m-%d %H:%M}"
    )

    print("\nRinging a 0.3-second demo alarm...")
    demo = Alarm(label="Demo alarm: stand up and stretch", seconds=0.3)
    wait_for_alarm(demo, sound="beep")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play an alarm after a delay or at a given time of day.",
        epilog="Examples: --in 90s | --in 1h30m | --at 07:30 | --at 7:30pm",
    )
    when = parser.add_mutually_exclusive_group()
    when.add_argument("-i", "--in", dest="delay", metavar="DURATION",
                      help="delay such as 90s, 10m, 1h30m, 1:30 (bare number = minutes)")
    when.add_argument("-a", "--at", metavar="TIME",
                      help="wall-clock time such as 07:30, 19:45 or 7:30pm")
    parser.add_argument("-m", "--message", help="message shown when the alarm fires")
    parser.add_argument("--sound", choices=("beep", "bell", "none"), default="beep",
                        help="how to signal the alarm (default: beep)")
    parser.add_argument("--demo", action="store_true",
                        help="run a fast scripted demonstration and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.delay and not args.at:
        try:
            args.delay = input("Alarm in how long? (e.g. 10m, 90s, 1:30): ")
            args.message = args.message or input("Message (blank for 'Wake up!'): ") or None
        except (EOFError, KeyboardInterrupt):
            print("\nNo alarm scheduled.")
            return 0

    try:
        alarm = build_alarm(args)
    except ValueError as exc:
        parser.error(str(exc))

    if alarm.target is not None:
        print(f"Alarm set for {alarm.target:%Y-%m-%d %H:%M} "
              f"(in {format_seconds(alarm.seconds)}).")
    else:
        print(f"Alarm set for {format_seconds(alarm.seconds)} from now.")

    try:
        wait_for_alarm(alarm, args.sound)
    except KeyboardInterrupt:
        print("\nAlarm cancelled.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
