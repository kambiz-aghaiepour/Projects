# TV Show Tracker

> Category: `Databases` · Project: `TV-Show-Tracker`

## Problem

Make an application which can search various online TV Guide sites, locate the
shows/times/channels and add them to a database application. The database can
send email reminders that a show is about to start.

## Features

- SQLite storage for shows and episodes, including network, status, premiere
  date, genres, and summary.
- TVmaze API integration (no API key): search shows, fetch a show with all
  episodes, and fetch a day's broadcast schedule.
- Every network call has a timeout and degrades gracefully: on failure the
  program says so and uses a bundled five-show / sixteen-episode sample
  catalogue. `--offline` skips the network entirely.
- Watchlist of unwatched shows with each show's next airing.
- Next-airing view over a configurable horizon, grouped by date.
- Episode listing and watch/unwatch/remove commands.
- Email reminder digest for upcoming watchlist episodes. Without SMTP options
  it prints a preview; with `--smtp-host` it sends via SMTP/STARTTLS (or
  implicit TLS with `--ssl`). The password is read from an environment variable
  and is never stored or printed.
- `--demo` loads the bundled catalogue into a temporary database and exercises
  watchlist, search, schedule, next-airing, and reminder preview entirely
  offline.

## Requirements

Python 3.10+ (standard library only). Network access is optional; TVmaze is
free and keyless. SMTP is optional and needs a reachable mail server.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --db tv.db --search "severance"
python3 solution.py --db tv.db --add 95396
python3 solution.py --db tv.db --all
python3 solution.py --db tv.db --watchlist
python3 solution.py --db tv.db --next 14
python3 solution.py --db tv.db --schedule 2026-11-03
python3 solution.py --db tv.db --episodes 95396
python3 solution.py --db tv.db --watch 95396
python3 solution.py --db tv.db --remind --days 7
```

- `--search TEXT` — query TVmaze; falls back to the sample catalogue offline.
- `--add ID` — add/refresh a show and its episodes by TVmaze id.
- `--offline` — never call the network; use the bundled sample.
- `--all`, `--watchlist` — list stored shows / unwatched shows with next airing.
- `--next [DAYS]` — watchlist episodes airing in the next N days (default 14).
- `--schedule [YYYY-MM-DD]` — broadcast schedule for a date (default today),
  with `--country` for the API query.
- `--watch ID`, `--unwatch ID`, `--remove ID` — manage the database.
- `--remind` with `--days N` — build the digest. Without `--smtp-host` it only
  prints a preview and exits 0.
- SMTP: `--smtp-host`, `--smtp-port` (default 587, or 465 with `--ssl`),
  `--smtp-user`, `--password-env` (default `SMTP_PASSWORD`), `--from`, `--to`
  (repeatable), `--ssl`, `--no-tls`.
- `--timeout` — network timeout in seconds (default 6).
- `--demo` — offline scripted demo.

## Example Output

```
TV Show Tracker — demo (offline bundled catalogue)
Loaded 5 shows and 16 episodes

--- WATCHLIST (today = 2026-11-02) ---
Watchlist (5 show(s)):
    ID  Show                          Network       Status     Next airing
  9004  Cosmos Rewind                 Docu+         Running    2026-11-05 S01E02 Voyager's Long Goodbye
  9002  Kitchen Lab                   Public One    Running    2026-11-08 S01E06 Fermentation
  9003  Night Shift                   Streamly      Running    2026-11-06 S03E05 Cold Open
  9005  Old Friends                   Retro Net     Ended      no upcoming episodes
  9001  The Signal                    Orbit TV      Running    2026-11-03 S02E02 The Carrier

--- NEXT AIRINGS: 14 days ---
Next airings for the watchlist (2026-11-02 + 14 day(s)):

Tuesday, Nov 03
  21:00  The Signal S02E02  The Carrier  [Orbit TV]

Thursday, Nov 05
  20:00  Cosmos Rewind S01E02  Voyager's Long Goodbye  [Docu+]
...

--- EMAIL REMINDER PREVIEW (not sent) ---
Subject: TV reminders: 3 episode(s) in the next 7 day(s)
Upcoming episodes for your watchlist (2026-11-02):

Tuesday, November 03, 2026
  21:00  The Signal S02E02 "The Carrier" on Orbit TV
...
```

## Implementation Notes

TVmaze responses are normalized into a small internal shape so the database and
offline sample share one code path. `urllib.request` is used with a custom
User-Agent and a timeout; `NetworkError` triggers the fallback message and
sample data. The sample IDs are 9001–9005, and its air dates are fixed in
November 2026 so the demo output is reproducible.

Shows are keyed by TVmaze id. `save_show` upserts metadata and episodes, but
preserves the `watched` flag. Episodes have a `(show_id, season, number)` unique
constraint, so refreshing a show is idempotent and does not duplicate rows.
"Next airing" is the earliest episode on or after today; reminders consider only
unwatched shows and include episodes airing today.

SMTP uses `EmailMessage` and `SMTP_SSL` or `SMTP` + `starttls`. Failure to
connect or authenticate is reported as an error without a traceback. The demo
never opens a network connection, sends no email, and writes only to a
temporary database.
