#!/usr/bin/env python3
"""Event Scheduler and Calendar: a SQLite-backed personal calendar.

Stores events with start/end times, notes, location, category and optional
recurrence (daily, weekly, monthly, yearly) plus per-event exception dates.
Provides month, week, and agenda views, full-text search, deletion, and iCalendar
(.ics) export that preserves recurrence rules and exceptions.
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Sequence

RECURRENCES = ("none", "daily", "weekly", "monthly", "yearly")
DEFAULT_DB = Path("events.db")
MAX_ITERATIONS = 5000
ISO_FORMAT = "%Y-%m-%d %H:%M"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    recurrence TEXT NOT NULL DEFAULT 'none',
    recur_until TEXT
);
CREATE TABLE IF NOT EXISTS exceptions (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    skip_date TEXT NOT NULL,
    PRIMARY KEY (event_id, skip_date)
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_ts);
"""


@dataclass
class Event:
    """A stored event definition."""

    id: int
    title: str
    start: datetime
    end: datetime
    notes: str
    location: str
    category: str
    recurrence: str
    recur_until: date | None
    skips: frozenset[date]


@dataclass
class Occurrence:
    """One concrete instance of an event."""

    event_id: int
    title: str
    start: datetime
    end: datetime
    notes: str
    location: str
    category: str


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (and initialize) the calendar database."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def parse_datetime(text: str, label: str = "datetime") -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' or the ISO 'T' variant."""
    cleaned = text.strip().replace("T", " ")
    for fmt in (ISO_FORMAT, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise ValueError(f"{label} must be 'YYYY-MM-DD HH:MM', got '{text}'")


def parse_date(text: str, label: str = "date") -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got '{text}'") from exc


def add_months(moment: datetime, months: int) -> datetime:
    """Add months, clamping the day to the target month's length."""
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def add_years(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:  # 29 February in a non-leap year
        return moment.replace(year=moment.year + years, day=28)


def load_events(conn: sqlite3.Connection) -> list[Event]:
    """Load every event with its exception dates."""
    skip_rows = conn.execute("SELECT event_id, skip_date FROM exceptions").fetchall()
    skips: dict[int, set[date]] = {}
    for row in skip_rows:
        skips.setdefault(row["event_id"], set()).add(date.fromisoformat(row["skip_date"]))
    events = []
    for row in conn.execute("SELECT * FROM events ORDER BY start_ts"):
        events.append(Event(
            id=row["id"], title=row["title"],
            start=parse_datetime(row["start_ts"]), end=parse_datetime(row["end_ts"]),
            notes=row["notes"], location=row["location"], category=row["category"],
            recurrence=row["recurrence"],
            recur_until=date.fromisoformat(row["recur_until"]) if row["recur_until"] else None,
            skips=frozenset(skips.get(row["id"], set())),
        ))
    return events


def event_occurrences(event: Event, range_start: datetime, range_end: datetime) -> list[Occurrence]:
    """Expand one event into occurrences overlapping the given range."""
    duration = event.end - event.start
    if event.recurrence == "none":
        if event.start <= range_end and event.end >= range_start:
            return [Occurrence(event.id, event.title, event.start, event.end,
                               event.notes, event.location, event.category)]
        return []

    hard_end = min(event.recur_until, range_end.date()) if event.recur_until else range_end.date()
    if event.start.date() > hard_end:
        return []
    results: list[Occurrence] = []
    for index in range(MAX_ITERATIONS):
        if event.recurrence == "daily":
            start = event.start + timedelta(days=index)
        elif event.recurrence == "weekly":
            start = event.start + timedelta(weeks=index)
        elif event.recurrence == "monthly":
            start = add_months(event.start, index)
        else:
            start = add_years(event.start, index)
        if start.date() > hard_end:
            break
        end = start + duration
        if end < range_start:
            continue
        if start > range_end:
            break
        if start.date() in event.skips:
            continue
        results.append(Occurrence(event.id, event.title, start, end,
                                  event.notes, event.location, event.category))
    return results


def occurrences_between(conn: sqlite3.Connection, range_start: datetime,
                        range_end: datetime) -> list[Occurrence]:
    """All occurrences from all events in the range, sorted by start time."""
    occurrences: list[Occurrence] = []
    for event in load_events(conn):
        occurrences.extend(event_occurrences(event, range_start, range_end))
    return sorted(occurrences, key=lambda item: (item.start, item.title))


def recurrence_label(event: Event) -> str:
    if event.recurrence == "none":
        return "one-off"
    suffix = f" until {event.recur_until.isoformat()}" if event.recur_until else ""
    return f"{event.recurrence}{suffix}"


def add_event(conn: sqlite3.Connection, title: str, start: datetime, end: datetime, *,
              notes: str = "", location: str = "", category: str = "general",
              recurrence: str = "none", until: date | None = None,
              skips: Sequence[date] = ()) -> int:
    """Insert an event and its exceptions; return the new id."""
    if not title.strip():
        raise ValueError("title must not be empty")
    if end <= start:
        raise ValueError("end must be after start")
    if recurrence not in RECURRENCES:
        raise ValueError(f"recurrence must be one of {', '.join(RECURRENCES)}")
    if until and until < start.date():
        raise ValueError("--until cannot be before the first occurrence")
    if recurrence == "none" and until:
        raise ValueError("--until only applies to recurring events")
    cursor = conn.execute(
        """INSERT INTO events(title, start_ts, end_ts, notes, location, category,
                              recurrence, recur_until)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title.strip(), start.strftime(ISO_FORMAT), end.strftime(ISO_FORMAT),
         notes.strip(), location.strip(), category.strip() or "general", recurrence,
         until.isoformat() if until else None),
    )
    event_id = int(cursor.lastrowid or 0)
    conn.executemany(
        "INSERT OR IGNORE INTO exceptions(event_id, skip_date) VALUES (?, ?)",
        [(event_id, day.isoformat()) for day in skips],
    )
    conn.commit()
    return event_id


def delete_event(conn: sqlite3.Connection, event_id: int) -> bool:
    cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    return cursor.rowcount > 0


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    first = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    return first, datetime(year, month, last_day, 23, 59, 59)


def group_by_day(occurrences: Sequence[Occurrence]) -> dict[date, list[Occurrence]]:
    """Assign each occurrence to every calendar day it overlaps."""
    grouped: dict[date, list[Occurrence]] = {}
    for occurrence in occurrences:
        first = occurrence.start.date()
        last = (occurrence.end - timedelta(seconds=1)).date()
        for offset in range(max(0, (last - first).days) + 1):
            grouped.setdefault(first + timedelta(days=offset), []).append(occurrence)
    for entries in grouped.values():
        entries.sort(key=lambda item: (item.start, item.title))
    return grouped


def render_month(occurrences: Sequence[Occurrence], year: int, month: int,
                 width: int = 19) -> str:
    """Render a Monday-first month grid with up to two titles per day."""
    by_day = group_by_day(occurrences)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    month_name = calendar.month_name[month]
    lines = [f"{month_name} {year}", ""]
    lines.append("|" + "|".join(name.center(width) for name in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")) + "|")
    border = "+" + "+".join("-" * width for _ in range(7)) + "+"
    for week in weeks:
        cells: list[list[str]] = []
        for day in week:
            entries = by_day.get(day, [])
            label = f"{day.day:2d}"
            if day.month != month:
                label = f"{calendar.month_abbr[day.month]} {day.day:2d}"
            cell = [label]
            for occurrence in entries[:2]:
                prefix = f"{occurrence.start:%H:%M}" if occurrence.start.date() == day else "  .."
                cell.append(f"{prefix} {occurrence.title}"[: width - 1])
            if len(entries) > 2:
                cell.append(f"+{len(entries) - 2} more")
            cells.append(cell)
        lines.append(border)
        height = max(len(cell) for cell in cells)
        for row in range(height):
            values = [cell[row] if row < len(cell) else "" for cell in cells]
            lines.append("|" + "|".join(value.ljust(width)[:width] for value in values) + "|")
    lines.append(border)
    return "\n".join(lines)


def render_week(conn: sqlite3.Connection, any_day: date) -> str:
    """Render a Monday-to-Sunday agenda for the week containing *any_day*."""
    monday = any_day - timedelta(days=any_day.weekday())
    start = datetime.combine(monday, time.min)
    end = start + timedelta(days=7) - timedelta(seconds=1)
    occurrences = occurrences_between(conn, start, end)
    by_day = group_by_day(occurrences)
    lines = [f"Week of {monday.isoformat()} to {(monday + timedelta(days=6)).isoformat()}"]
    for offset in range(7):
        day = monday + timedelta(days=offset)
        entries = by_day.get(day, [])
        lines.append(f"\n{day.strftime('%a %Y-%m-%d')}  ({len(entries)} event(s))")
        if not entries:
            lines.append("  (free)")
            continue
        day_start = datetime.combine(day, time.min)
        day_end = datetime.combine(day, time(23, 59, 59))
        for occurrence in entries:
            clipped_start = max(occurrence.start, day_start)
            clipped_end = min(occurrence.end, day_end)
            if clipped_start == day_start and clipped_end == day_end:
                when = "all day"
            else:
                when = f"{clipped_start:%H:%M}-{clipped_end:%H:%M}"
            place = f" @ {occurrence.location}" if occurrence.location else ""
            lines.append(f"  {when}  {occurrence.title}{place}  [{occurrence.category}]")
            if occurrence.notes:
                lines.append(f"      {occurrence.notes}")
    return "\n".join(lines)


def render_agenda(conn: sqlite3.Connection, start_day: date, days: int = 7) -> str:
    """Render a chronological agenda for *days* days starting at *start_day*."""
    start = datetime.combine(start_day, time.min)
    end = start + timedelta(days=max(1, days)) - timedelta(seconds=1)
    occurrences = occurrences_between(conn, start, end)
    lines = [f"Agenda: {start_day.isoformat()} + {max(1, days)} day(s)"]
    if not occurrences:
        lines.append("  (no events)")
        return "\n".join(lines)
    current: date | None = None
    for occurrence in occurrences:
        day = occurrence.start.date()
        if day != current:
            current = day
            lines.append(f"\n{day.strftime('%A, %B %d, %Y')}")
        place = f" @ {occurrence.location}" if occurrence.location else ""
        lines.append(f"  {occurrence.start:%H:%M}-{occurrence.end:%H:%M}  "
                     f"{occurrence.title}{place}  [{occurrence.category}]")
        if occurrence.end.date() > day:
            lines.append(f"      continues through {occurrence.end:%a %b %d, %H:%M}")
        if occurrence.notes:
            lines.append(f"      {occurrence.notes}")
    return "\n".join(lines)


def list_events(conn: sqlite3.Connection) -> str:
    """Render all event definitions (not expanded occurrences)."""
    events = load_events(conn)
    if not events:
        return "No events stored."
    lines = ["Stored events:", f"{'ID':>3}  {'Start':16}  {'Title':30}  {'Category':12}  Recurrence"]
    for event in events:
        skips = f", {len(event.skips)} skip(s)" if event.skips else ""
        lines.append(f"{event.id:>3}  {event.start.strftime(ISO_FORMAT):16}  "
                     f"{event.title[:30]:30}  {event.category[:12]:12}  "
                     f"{recurrence_label(event)}{skips}")
    return "\n".join(lines)


def search_events(conn: sqlite3.Connection, term: str) -> str:
    """Search title, notes, location and category with LIKE."""
    if not term.strip():
        raise ValueError("search term must not be empty")
    pattern = f"%{term.strip()}%"
    rows = conn.execute(
        """SELECT * FROM events
           WHERE title LIKE ? OR notes LIKE ? OR location LIKE ? OR category LIKE ?
           ORDER BY start_ts""", (pattern, pattern, pattern, pattern)
    ).fetchall()
    if not rows:
        return f"No events match '{term}'."
    lines = [f"Matches for '{term}':"]
    for row in rows:
        lines.append(f"  #{row['id']}  {row['start_ts']}  {row['title']}  "
                     f"[{row['category']}]  ({row['recurrence']})")
        if row["location"]:
            lines.append(f"      at {row['location']}")
        if row["notes"]:
            lines.append(f"      {row['notes']}")
    return "\n".join(lines)


def ics_escape(text: str) -> str:
    """Escape a text value for an iCalendar property."""
    return (text.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def export_ics(conn: sqlite3.Connection, path: Path) -> tuple[int, Path]:
    """Write all events to an iCalendar file; return event count and path."""
    events = load_events(conn)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Event Scheduler//EN",
             "CALSCALE:GREGORIAN"]
    frequency = {"daily": "DAILY", "weekly": "WEEKLY",
                 "monthly": "MONTHLY", "yearly": "YEARLY"}
    for event in events:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:event-{event.id}@event-scheduler.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{event.start:%Y%m%dT%H%M%S}",
            f"DTEND:{event.end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{ics_escape(event.title)}",
        ])
        if event.notes:
            lines.append(f"DESCRIPTION:{ics_escape(event.notes)}")
        if event.location:
            lines.append(f"LOCATION:{ics_escape(event.location)}")
        lines.append(f"CATEGORIES:{ics_escape(event.category.upper())}")
        if event.recurrence in frequency:
            rule = f"RRULE:FREQ={frequency[event.recurrence]}"
            if event.recur_until:
                rule += f";UNTIL={event.recur_until:%Y%m%d}T235959"
            lines.append(rule)
            for skip in sorted(event.skips):
                lines.append(f"EXDATE:{skip:%Y%m%d}T{event.start:%H%M%S}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return len(events), path


def seed_demo(conn: sqlite3.Connection) -> None:
    """Populate a fixed November 2026 calendar with recurring events."""
    add_event(conn, "Team standup", datetime(2026, 11, 2, 9, 0), datetime(2026, 11, 2, 9, 30),
              notes="Daily blockers and priorities", location="Video call",
              category="work", recurrence="weekly", until=date(2026, 12, 28),
              skips=[date(2026, 11, 16)])
    add_event(conn, "Book club", datetime(2026, 11, 5, 19, 0), datetime(2026, 11, 5, 21, 0),
              notes="Discuss 'Designing Data-Intensive Applications'", location="City library",
              category="social", recurrence="monthly", until=date(2027, 6, 5))
    add_event(conn, "Dentist appointment", datetime(2026, 11, 10, 14, 0),
              datetime(2026, 11, 10, 15, 0), notes="Bring insurance card",
              location="Smile Clinic", category="health")
    add_event(conn, "Ada's birthday", datetime(2026, 11, 12, 18, 0),
              datetime(2026, 11, 12, 22, 0), location="Home", category="personal",
              recurrence="yearly")
    add_event(conn, "Morning run", datetime(2026, 11, 2, 7, 0), datetime(2026, 11, 2, 7, 45),
              location="Riverside park", category="health", recurrence="daily",
              until=date(2026, 11, 8))
    add_event(conn, "Tech conference", datetime(2026, 11, 20, 9, 0),
              datetime(2026, 11, 22, 17, 0), notes="Three-day conference, Hall B",
              location="Convention Centre", category="work")


def run_demo() -> int:
    """Build a sample calendar and exercise every view, search, and ICS export."""
    print("Event Scheduler and Calendar — demo")
    with tempfile.TemporaryDirectory(prefix="event-calendar-") as tmp:
        db_path = Path(tmp) / "events.db"
        with connect(db_path) as conn:
            seed_demo(conn)
            print(f"Added {len(load_events(conn))} events (weekly, monthly, yearly, daily, one-off)\n")
            print("--- MONTH VIEW: November 2026 ---")
            start, end = month_bounds(2026, 11)
            print(render_month(occurrences_between(conn, start, end), 2026, 11))
            print("\n--- WEEK VIEW: week of 2026-11-09 ---")
            print(render_week(conn, date(2026, 11, 9)))
            print("\n--- AGENDA: 2026-11-09 + 10 days ---")
            print(render_agenda(conn, date(2026, 11, 9), 10))
            print("\n--- SEARCH: 'library' ---")
            print(search_events(conn, "library"))
            print("\n--- ICS EXPORT ---")
            count, path = export_ics(conn, Path(tmp) / "calendar.ics")
            content = path.read_text(encoding="utf-8")
            print(f"Exported {count} events to calendar.ics ({len(content):,} bytes)")
            print("Contains RRULE:", "RRULE:FREQ=WEEKLY" in content,
                  "| Contains EXDATE:", "EXDATE:20261116T090000" in content)
            print("Standup occurrences in November:", sum(
                1 for occurrence in occurrences_between(conn, start, end)
                if occurrence.title == "Team standup"))
        print("\nDemo complete. Real use: python3 solution.py --db my-calendar.db --month 2026-11")
    return 0


def interactive(db_path: Path) -> int:
    """Simple menu-driven calendar."""
    with connect(db_path) as conn:
        while True:
            print("\n1) add  2) list  3) month  4) week  5) agenda  6) search  7) export ICS  0) quit")
            choice = input("Choose: ").strip()
            try:
                if choice == "0":
                    return 0
                if choice == "1":
                    title = input("Title: ")
                    start = parse_datetime(input("Start (YYYY-MM-DD HH:MM): "), "start")
                    end_text = input("End (blank = +1 hour): ").strip()
                    end = parse_datetime(end_text, "end") if end_text else start + timedelta(hours=1)
                    recurrence = input(f"Recurrence {RECURRENCES} [none]: ").strip() or "none"
                    until_text = input("Repeat until (YYYY-MM-DD, blank = none): ").strip()
                    notes = input("Notes: ")
                    location = input("Location: ")
                    category = input("Category [general]: ") or "general"
                    event_id = add_event(
                        conn, title, start, end, notes=notes, location=location,
                        category=category, recurrence=recurrence,
                        until=parse_date(until_text, "until") if until_text else None,
                    )
                    print(f"Added event #{event_id}.")
                elif choice == "2":
                    print(list_events(conn))
                elif choice == "3":
                    year, month = input("Month (YYYY-MM): ").split("-")
                    start, end = month_bounds(int(year), int(month))
                    print(render_month(occurrences_between(conn, start, end), int(year), int(month)))
                elif choice == "4":
                    print(render_week(conn, parse_date(input("Any day (YYYY-MM-DD): "))))
                elif choice == "5":
                    day = parse_date(input("Start day (YYYY-MM-DD): "))
                    days = int(input("Days [7]: ") or "7")
                    print(render_agenda(conn, day, days))
                elif choice == "6":
                    print(search_events(conn, input("Search: ")))
                elif choice == "7":
                    count, path = export_ics(conn, Path(input("Output file [calendar.ics]: ") or "calendar.ics"))
                    print(f"Exported {count} events to {path}.")
                else:
                    print("Unknown choice.")
            except (ValueError, OSError) as exc:
                print(f"error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="SQLite event calendar with recurrence, month/week/agenda views, search, and ICS export.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database (default: events.db)")
    parser.add_argument("--add", action="store_true", help="add an event")
    parser.add_argument("--title", help="event title (with --add)")
    parser.add_argument("--start", metavar="'YYYY-MM-DD HH:MM'", help="start date and time")
    parser.add_argument("--end", metavar="'YYYY-MM-DD HH:MM'", help="end date and time (default: +1 hour)")
    parser.add_argument("--notes", default="", help="event notes")
    parser.add_argument("--location", default="", help="event location")
    parser.add_argument("--category", default="general", help="event category")
    parser.add_argument("--recurrence", choices=RECURRENCES, default="none")
    parser.add_argument("--until", metavar="YYYY-MM-DD", help="last recurrence date")
    parser.add_argument("--skip", action="append", default=[], metavar="YYYY-MM-DD",
                        help="skip one recurrence date (repeatable)")
    parser.add_argument("--list", action="store_true", help="list stored event definitions")
    parser.add_argument("--month", metavar="YYYY-MM", help="show a month grid")
    parser.add_argument("--week", metavar="YYYY-MM-DD", help="show the week containing a date")
    parser.add_argument("--agenda", nargs="?", const=7, type=int, metavar="DAYS",
                        help="agenda starting today (or use --agenda-start)")
    parser.add_argument("--agenda-start", metavar="YYYY-MM-DD", help="agenda start date")
    parser.add_argument("--search", metavar="TEXT", help="search title, notes, location, category")
    parser.add_argument("--delete", type=int, metavar="ID", help="delete an event by id")
    parser.add_argument("--ics", type=Path, metavar="FILE", help="export all events as iCalendar")
    parser.add_argument("--demo", action="store_true", help="run the scripted November 2026 demo")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if len(sys.argv) == 1 and argv is None:
        return interactive(args.db)
    try:
        with connect(args.db) as conn:
            if args.add:
                if not args.title or not args.start:
                    parser.error("--add requires --title and --start")
                start = parse_datetime(args.start, "--start")
                end = parse_datetime(args.end, "--end") if args.end else start + timedelta(hours=1)
                event_id = add_event(
                    conn, args.title, start, end, notes=args.notes,
                    location=args.location, category=args.category,
                    recurrence=args.recurrence,
                    until=parse_date(args.until, "--until") if args.until else None,
                    skips=[parse_date(day, "--skip") for day in args.skip],
                )
                print(f"Added event #{event_id}.")
                return 0
            if args.delete is not None:
                deleted = delete_event(conn, args.delete)
                if deleted:
                    print(f"Deleted event #{args.delete}.")
                    return 0
                print(f"error: event #{args.delete} not found", file=sys.stderr)
                return 2
            if args.list:
                print(list_events(conn))
                return 0
            if args.month:
                year_text, month_text = args.month.split("-", 1)
                start, end = month_bounds(int(year_text), int(month_text))
                print(render_month(occurrences_between(conn, start, end),
                                   int(year_text), int(month_text)))
                return 0
            if args.week:
                print(render_week(conn, parse_date(args.week, "--week")))
                return 0
            if args.agenda is not None:
                start_day = parse_date(args.agenda_start, "--agenda-start") if args.agenda_start else date.today()
                print(render_agenda(conn, start_day, args.agenda))
                return 0
            if args.search is not None:
                print(search_events(conn, args.search))
                return 0
            if args.ics:
                count, path = export_ics(conn, args.ics)
                print(f"Exported {count} events to {path}.")
                return 0
            parser.print_help()
            return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
