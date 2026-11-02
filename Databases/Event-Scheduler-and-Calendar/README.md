# Event Scheduler and Calendar

> Category: `Databases` · Project: `Event-Scheduler-and-Calendar`

## Problem

Make an application which allows the user to enter a date and time of an event,
event notes and then schedule those events on a calendar. The user can browse
or search the calendar. Optional: recurring events.

## Features

- SQLite storage for events: title, start, end, notes, location, category.
- Recurrence: `daily`, `weekly`, `monthly`, `yearly`, with an optional end date.
- Exception dates (`--skip`) for recurring series, preserved in views and
  iCalendar export.
- Three browsing modes:
  - **month** — Monday-first grid with event titles (multi-day events appear on
    every day they cover);
  - **week** — day-by-day schedule with times, locations, and notes;
  - **agenda** — chronological list starting on any date for N days.
- Search across title, notes, location, and category.
- ICS export with `RRULE` and `EXDATE`, importable into Google Calendar,
  Apple Calendar, Thunderbird, and other iCalendar clients.
- Menu-driven interactive mode when run with no arguments.
- `--demo` builds a fixed November 2026 calendar with weekly, monthly, yearly,
  daily, and one-off events (including a skipped recurrence).

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo

python3 solution.py --db my-calendar.db --add --title "Team standup" \
    --start "2026-11-02 09:00" --end "2026-11-02 09:30" \
    --notes "Blockers" --location "Video call" --category work \
    --recurrence weekly --until 2026-12-28 --skip 2026-11-16

python3 solution.py --db my-calendar.db --month 2026-11
python3 solution.py --db my-calendar.db --week 2026-11-09
python3 solution.py --db my-calendar.db --agenda 14 --agenda-start 2026-11-09
python3 solution.py --db my-calendar.db --search library
python3 solution.py --db my-calendar.db --ics calendar.ics
```

- `--db` — SQLite file (default `events.db`; created on first use).
- `--add` — add an event; requires `--title` and `--start`. `--end` defaults to
  one hour after the start.
- `--recurrence` — `none` (default), `daily`, `weekly`, `monthly`, `yearly`.
- `--until` — last date of the recurrence (`YYYY-MM-DD`).
- `--skip` — skip one occurrence date; repeat the option for multiple dates.
- `--list` — show stored event definitions, including recurrence and skips.
- `--month YYYY-MM`, `--week YYYY-MM-DD`, `--agenda [DAYS]` — calendar views.
- `--delete ID` — remove an event and its exceptions.
- `--ics FILE` — export every event as iCalendar.
- `--demo` — scripted sample calendar in a temporary database.

Dates and times use `YYYY-MM-DD HH:MM` (the ISO `T` separator is also accepted).

## Example Output

```
Event Scheduler and Calendar — demo
Added 6 events (weekly, monthly, yearly, daily, one-off)

--- MONTH VIEW: November 2026 ---
November 2026

|        Mon        |        Tue        |        Wed        |        Thu        |        Fri        |        Sat        |        Sun        |
+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+
|Oct 26             |Oct 27             |Oct 28             |Oct 29             |Oct 30             |Oct 31             | 1                 |
+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+
| 2                 | 3                 | 4                 | 5                 | 6                 | 7                 | 8                 |
|07:00 Morning run  |07:00 Morning run  |07:00 Morning run  |07:00 Morning run  |07:00 Morning run  |07:00 Morning run  |07:00 Morning run  |
|09:00 Team standup |                   |                   |19:00 Book club    |                   |                   |                   |
...
|16                 |17                 |18                 |19                 |20                 |21                 |22                 |
|                   |                   |                   |                   |09:00 Tech confere |  .. Tech conferen |  .. Tech conferen |
+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+-------------------+

--- WEEK VIEW: week of 2026-11-09 ---
Mon 2026-11-09  (1 event(s))
  09:00-09:30  Team standup @ Video call  [work]
      Daily blockers and priorities

Tue 2026-11-10  (1 event(s))
  14:00-15:00  Dentist appointment @ Smile Clinic  [health]

--- SEARCH: 'library' ---
Matches for 'library':
  #2  2026-11-05 19:00  Book club  [social]  (monthly)
      at City library

--- ICS EXPORT ---
Exported 6 events to calendar.ics (1,572 bytes)
Contains RRULE: True | Contains EXDATE: True
Standup occurrences in November: 4
```

## Implementation Notes

Occurrences are expanded in Python from each event's base start, not stored
per-date. Daily/weekly recurrences add fixed timedeltas; monthly and yearly
recurrences recompute from the base date and clamp to the target month's last
day (31 Jan → 28/29 Feb), avoiding drift. Each occurrence is skipped when its
start date appears in the event's exception set, and expansion stops at
`--until`, the requested range, or a safety cap of 5,000 iterations per event.

Views group occurrences by every day they overlap. The month grid truncates long
titles to cell width; the week view clips multi-day events to each day's
boundaries and labels fully covered days "all day". ICS export uses floating
local times (no VTIMEZONE), writes `RRULE` with `UNTIL`, and emits `EXDATE` for
exceptions. Long ICS lines are not folded at 75 octets; clients generally
accept this, but it is the main compatibility limitation.

The database enables `PRAGMA foreign_keys` so deleting an event cascades to its
exceptions.
