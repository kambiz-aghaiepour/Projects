#!/usr/bin/env python3
"""TV Show Tracker: track shows and episodes with optional TVmaze lookups.

Shows and episodes live in SQLite.  Search and episode metadata can come from
the public TVmaze API (no key required) with a short timeout; when the network
is unavailable the program falls back to a bundled sample catalogue so every
command, including the demo, still works offline.  The watchlist drives a
next-airing view and optional SMTP email reminders.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import smtplib
import sqlite3
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable, Sequence

DEFAULT_DB = Path("tvshows.db")
API_ROOT = "https://api.tvmaze.com"
USER_AGENT = "tv-show-tracker/1.0 (educational project)"
DEMO_TODAY = date(2026, 11, 2)
TAG_RE = re.compile(r"<[^>]+>")

SAMPLE_SHOWS: list[dict[str, Any]] = [
    {
        "id": 9001, "name": "The Signal", "network": "Orbit TV", "status": "Running",
        "premiered": "2025-09-12", "genres": ["Drama", "Science-Fiction"],
        "summary": "A radio astronomer intercepts a message that predicts the next day's news.",
        "url": "https://example.invalid/shows/the-signal",
    },
    {
        "id": 9002, "name": "Kitchen Lab", "network": "Public One", "status": "Running",
        "premiered": "2026-09-06", "genres": ["Food", "Reality"],
        "summary": "Chefs test unusual ingredients under laboratory conditions.",
        "url": "https://example.invalid/shows/kitchen-lab",
    },
    {
        "id": 9003, "name": "Night Shift", "network": "Streamly", "status": "Running",
        "premiered": "2024-02-18", "genres": ["Crime", "Thriller"],
        "summary": "A night-duty detective unit works the cases nobody else wants.",
        "url": "https://example.invalid/shows/night-shift",
    },
    {
        "id": 9004, "name": "Cosmos Rewind", "network": "Docu+", "status": "Running",
        "premiered": "2026-10-29", "genres": ["Documentary", "Science"],
        "summary": "A retrospective of astronomical discoveries, one mission per episode.",
        "url": "https://example.invalid/shows/cosmos-rewind",
    },
    {
        "id": 9005, "name": "Old Friends", "network": "Retro Net", "status": "Ended",
        "premiered": "2021-01-10", "genres": ["Comedy"],
        "summary": "Four friends reopen their favourite cafe. The series concluded in 2024.",
        "url": "https://example.invalid/shows/old-friends",
    },
]

SAMPLE_EPISODES: dict[int, list[dict[str, Any]]] = {
    9001: [
        {"season": 2, "number": 1, "name": "Dead Air", "airdate": "2026-10-27", "airtime": "21:00", "runtime": 52},
        {"season": 2, "number": 2, "name": "The Carrier", "airdate": "2026-11-03", "airtime": "21:00", "runtime": 50},
        {"season": 2, "number": 3, "name": "Static", "airdate": "2026-11-10", "airtime": "21:00", "runtime": 51},
        {"season": 2, "number": 4, "name": "Frequencies", "airdate": "2026-11-17", "airtime": "21:00", "runtime": 49},
    ],
    9002: [
        {"season": 1, "number": 5, "name": "Smoke Point", "airdate": "2026-11-01", "airtime": "10:00", "runtime": 30},
        {"season": 1, "number": 6, "name": "Fermentation", "airdate": "2026-11-08", "airtime": "10:00", "runtime": 30},
        {"season": 1, "number": 7, "name": "Emulsions", "airdate": "2026-11-15", "airtime": "10:00", "runtime": 30},
        {"season": 1, "number": 8, "name": "The Final Plate", "airdate": "2026-11-22", "airtime": "10:00", "runtime": 30},
    ],
    9003: [
        {"season": 3, "number": 4, "name": "Third Watch", "airdate": "2026-10-30", "airtime": "22:00", "runtime": 44},
        {"season": 3, "number": 5, "name": "Cold Open", "airdate": "2026-11-06", "airtime": "22:00", "runtime": 44},
        {"season": 3, "number": 6, "name": "Underpass", "airdate": "2026-11-13", "airtime": "22:00", "runtime": 45},
        {"season": 3, "number": 7, "name": "Last Call", "airdate": "2026-11-20", "airtime": "22:00", "runtime": 43},
    ],
    9004: [
        {"season": 1, "number": 2, "name": "Voyager's Long Goodbye", "airdate": "2026-11-05", "airtime": "20:00", "runtime": 48},
        {"season": 1, "number": 3, "name": "The Infrared Sky", "airdate": "2026-11-12", "airtime": "20:00", "runtime": 47},
    ],
    9005: [
        {"season": 4, "number": 9, "name": "One More Coffee", "airdate": "2024-05-16", "airtime": "20:30", "runtime": 25},
        {"season": 4, "number": 10, "name": "Closing Time", "airdate": "2024-05-23", "airtime": "20:30", "runtime": 28},
    ],
}


class NetworkError(RuntimeError):
    """A TVmaze request failed (offline, timeout, bad response)."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS shows (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    network TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    premiered TEXT,
    genres TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    watched INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
    season INTEGER NOT NULL,
    number INTEGER NOT NULL,
    name TEXT NOT NULL,
    airdate TEXT,
    airtime TEXT,
    runtime INTEGER,
    UNIQUE(show_id, season, number)
);
CREATE INDEX IF NOT EXISTS idx_episodes_airdate ON episodes(airdate);
"""


@dataclass
class Show:
    id: int
    name: str
    network: str
    status: str
    premiered: str
    genres: str
    summary: str
    url: str
    watched: bool


def strip_tags(text: str | None) -> str:
    """Remove TVmaze's HTML from summaries."""
    if not text:
        return ""
    return html.unescape(TAG_RE.sub("", text)).strip()


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def api_get(path: str, params: dict[str, Any] | None = None,
            timeout: float = 6.0) -> Any:
    """GET a TVmaze API path and decode JSON."""
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    request = urllib.request.Request(API_ROOT + path + query, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            ValueError) as exc:
        raise NetworkError(str(exc) or exc.__class__.__name__) from exc


def normalize_show(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a TVmaze show object to the local shape."""
    network = raw.get("network") or raw.get("webChannel") or {}
    return {
        "id": int(raw["id"]),
        "name": raw.get("name") or "Unknown",
        "network": network.get("name") or "Unknown",
        "status": raw.get("status") or "Unknown",
        "premiered": raw.get("premiered") or "",
        "genres": list(raw.get("genres") or []),
        "summary": strip_tags(raw.get("summary")),
        "url": raw.get("url") or "",
    }


def normalize_episode(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "season": int(raw.get("season") or 0),
        "number": int(raw.get("number") or 0),
        "name": raw.get("name") or "TBA",
        "airdate": raw.get("airdate") or "",
        "airtime": raw.get("airtime") or "",
        "runtime": int(raw["runtime"]) if raw.get("runtime") else None,
    }


def search_api(query: str, timeout: float = 6.0) -> list[dict[str, Any]]:
    results = api_get("/search/shows", {"q": query}, timeout=timeout)
    return [normalize_show(item["show"]) for item in results if item.get("show")]


def fetch_show_api(show_id: int, timeout: float = 6.0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    show = normalize_show(api_get(f"/shows/{show_id}", timeout=timeout))
    episodes = [normalize_episode(item)
                for item in api_get(f"/shows/{show_id}/episodes", timeout=timeout)]
    return show, episodes


def schedule_api(day: date, country: str = "US", timeout: float = 6.0) -> list[dict[str, Any]]:
    payload = api_get("/schedule", {"date": day.isoformat(), "country": country}, timeout=timeout)
    entries = []
    for item in payload:
        show = normalize_show(item["show"])
        episode = normalize_episode(item)
        entries.append({"show": show, "episode": episode})
    return entries


def search_sample(query: str) -> list[dict[str, Any]]:
    needle = query.lower().strip()
    matches = []
    for show in SAMPLE_SHOWS:
        haystack = " ".join([show["name"], show["summary"], " ".join(show["genres"]),
                             show["network"]]).lower()
        if needle in haystack:
            matches.append(dict(show))
    return matches


def sample_show(show_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    for show in SAMPLE_SHOWS:
        if show["id"] == show_id:
            return dict(show), [dict(episode) for episode in SAMPLE_EPISODES.get(show_id, [])]
    return None


def schedule_sample(day: date) -> list[dict[str, Any]]:
    entries = []
    for show_id, episodes in SAMPLE_EPISODES.items():
        show = next(item for item in SAMPLE_SHOWS if item["id"] == show_id)
        for episode in episodes:
            if episode["airdate"] == day.isoformat():
                entries.append({"show": dict(show), "episode": dict(episode)})
    return entries


def genres_text(genres: Iterable[str]) -> str:
    return ", ".join(genre for genre in genres if genre)


def save_show(conn: sqlite3.Connection, show: dict[str, Any],
              episodes: Sequence[dict[str, Any]]) -> bool:
    """Insert or refresh a show and its episodes; return True if newly added."""
    existing = conn.execute("SELECT id FROM shows WHERE id = ?", (show["id"],)).fetchone()
    genres = show.get("genres") or []
    conn.execute(
        """INSERT INTO shows(id, name, network, status, premiered, genres, summary, url, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, network=excluded.network,
               status=excluded.status, premiered=excluded.premiered, genres=excluded.genres,
               summary=excluded.summary, url=excluded.url""",
        (int(show["id"]), show["name"], show.get("network", ""), show.get("status", ""),
         show.get("premiered") or None, genres_text(genres), show.get("summary", ""),
         show.get("url", ""), date.today().isoformat()),
    )
    for episode in episodes:
        conn.execute(
            """INSERT INTO episodes(show_id, season, number, name, airdate, airtime, runtime)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(show_id, season, number) DO UPDATE SET name=excluded.name,
                   airdate=excluded.airdate, airtime=excluded.airtime, runtime=excluded.runtime""",
            (int(show["id"]), episode["season"], episode["number"], episode["name"],
             episode.get("airdate") or None, episode.get("airtime") or None,
             episode.get("runtime")),
        )
    conn.commit()
    return existing is None


def load_shows(conn: sqlite3.Connection, watched: bool | None = None) -> list[Show]:
    query = "SELECT * FROM shows"
    params: tuple[Any, ...] = ()
    if watched is not None:
        query += " WHERE watched = ?"
        params = (1 if watched else 0,)
    query += " ORDER BY name COLLATE NOCASE"
    return [
        Show(int(row["id"]), row["name"], row["network"], row["status"],
             row["premiered"] or "", row["genres"], row["summary"], row["url"],
             bool(row["watched"]))
        for row in conn.execute(query, params)
    ]


def set_watched(conn: sqlite3.Connection, show_id: int, watched: bool) -> bool:
    cursor = conn.execute("UPDATE shows SET watched = ? WHERE id = ?", (1 if watched else 0, show_id))
    conn.commit()
    return cursor.rowcount > 0


def remove_show(conn: sqlite3.Connection, show_id: int) -> bool:
    cursor = conn.execute("DELETE FROM shows WHERE id = ?", (show_id,))
    conn.commit()
    return cursor.rowcount > 0


def next_episode(conn: sqlite3.Connection, show_id: int, today: date) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT * FROM episodes WHERE show_id = ? AND airdate >= ?
           ORDER BY airdate, airtime LIMIT 1""", (show_id, today.isoformat())
    ).fetchone()


def watchlist_text(conn: sqlite3.Connection, today: date) -> str:
    shows = load_shows(conn, watched=False)
    if not shows:
        return "Watchlist is empty. Find a show with --search and add it with --add ID."
    lines = [f"Watchlist ({len(shows)} show(s)):", 
             f"{'ID':>6}  {'Show':28}  {'Network':12}  {'Status':14}  Next airing"]
    for show in shows:
        upcoming = next_episode(conn, show.id, today)
        if upcoming:
            next_text = f"{upcoming['airdate']} S{upcoming['season']:02d}E{upcoming['number']:02d} {upcoming['name']}"
        else:
            next_text = "no upcoming episodes"
        lines.append(f"{show.id:>6}  {show.name[:28]:28}  {show.network[:12]:12}  "
                     f"{show.status[:14]:14}  {next_text}")
    return "\n".join(lines)


def list_shows_text(conn: sqlite3.Connection) -> str:
    shows = load_shows(conn)
    if not shows:
        return "No shows stored yet. Use --search and --add ID."
    lines = [f"All shows ({len(shows)}):",
             f"{'ID':>6}  {'Show':28}  {'Network':12}  {'Status':14}  Watched"]
    for show in shows:
        lines.append(f"{show.id:>6}  {show.name[:28]:28}  {show.network[:12]:12}  "
                     f"{show.status[:14]:14}  {'yes' if show.watched else 'no'}")
    return "\n".join(lines)


def search_text(results: Sequence[dict[str, Any]], source: str) -> str:
    if not results:
        return f"No shows found (source: {source})."
    lines = [f"Search results ({source}):",
             f"{'ID':>6}  {'Show':30}  {'Network':12}  {'Status':14}  Genres"]
    for show in results:
        lines.append(f"{int(show['id']):>6}  {show['name'][:30]:30}  "
                     f"{show['network'][:12]:12}  {show['status'][:14]:14}  "
                     f"{genres_text(show.get('genres', []))[:30]}")
    lines.append("Add one with: --add ID")
    return "\n".join(lines)


def episodes_text(conn: sqlite3.Connection, show_id: int) -> str:
    show = conn.execute("SELECT name FROM shows WHERE id = ?", (show_id,)).fetchone()
    if not show:
        return f"error: show {show_id} is not in the database"
    rows = conn.execute(
        "SELECT * FROM episodes WHERE show_id = ? ORDER BY season, number", (show_id,)
    ).fetchall()
    lines = [f"Episodes for {show['name']}:"]
    for row in rows:
        lines.append(f"  S{row['season']:02d}E{row['number']:02d}  {row['airdate'] or 'TBA':10}  "
                     f"{row['name']}  ({row['runtime'] or '?'} min)")
    return "\n".join(lines)


def next_airings(conn: sqlite3.Connection, days: int, today: date) -> list[sqlite3.Row]:
    end = today + timedelta(days=max(1, days) - 1)
    return conn.execute(
        """SELECT e.*, s.name AS show_name, s.network
           FROM episodes e JOIN shows s ON s.id = e.show_id
           WHERE s.watched = 0 AND e.airdate BETWEEN ? AND ?
           ORDER BY e.airdate, e.airtime, s.name""",
        (today.isoformat(), end.isoformat()),
    ).fetchall()


def next_text(conn: sqlite3.Connection, days: int, today: date) -> str:
    rows = next_airings(conn, days, today)
    header = f"Next airings for the watchlist ({today.isoformat()} + {max(1, days)} day(s)):"
    if not rows:
        return header + "\n  (nothing scheduled; episodes may not be loaded yet)"
    lines = [header]
    current = ""
    for row in rows:
        if row["airdate"] != current:
            current = row["airdate"]
            lines.append(f"\n{date.fromisoformat(current):%A, %b %d}")
        lines.append(f"  {row['airtime'] or '--:--'}  {row['show_name']} "
                     f"S{row['season']:02d}E{row['number']:02d}  {row['name']}  [{row['network']}]")
    return "\n".join(lines)


def schedule_text(entries: Sequence[dict[str, Any]], day: date, source: str) -> str:
    lines = [f"Schedule for {day.isoformat()} ({source}):"]
    if not entries:
        return "\n".join(lines + ["  (no episodes listed)"])
    for entry in sorted(entries, key=lambda item: (item["episode"].get("airtime") or "99:99",
                                                   item["show"]["name"])):
        episode = entry["episode"]
        lines.append(f"  {episode.get('airtime') or '--:--'}  {entry['show']['name']}  "
                     f"S{episode['season']:02d}E{episode['number']:02d}  {episode['name']}  "
                     f"[{entry['show']['network']}]")
    return "\n".join(lines)


def build_reminder(conn: sqlite3.Connection, days: int, today: date) -> tuple[str, str]:
    """Build the subject and body for upcoming watchlist episodes."""
    rows = next_airings(conn, days, today)
    if not rows:
        return ("TV reminders: nothing upcoming",
                f"No watchlist episodes air in the next {max(1, days)} day(s).\n")
    subject = f"TV reminders: {len(rows)} episode(s) in the next {max(1, days)} day(s)"
    lines = [f"Upcoming episodes for your watchlist ({today.isoformat()}):", ""]
    current = ""
    for row in rows:
        if row["airdate"] != current:
            current = row["airdate"]
            lines.append(f"{date.fromisoformat(current):%A, %B %d, %Y}")
        lines.append(f"  {row['airtime'] or '--:--'}  {row['show_name']} "
                     f"S{row['season']:02d}E{row['number']:02d} \"{row['name']}\" "
                     f"on {row['network']}")
    lines.extend(["", "— sent by TV Show Tracker"])
    return subject, "\n".join(lines)


def send_email(subject: str, body: str, args: argparse.Namespace) -> None:
    """Send the reminder through SMTP, using STARTTLS unless disabled."""
    if not args.to:
        raise ValueError("--to is required when --smtp-host is set")
    if not args.sender:
        raise ValueError("--from is required when --smtp-host is set")
    password = os.environ.get(args.password_env, "")
    if args.smtp_user and not password and sys.stdin.isatty():
        import getpass
        password = getpass.getpass(f"SMTP password for {args.smtp_user}: ")
    port = args.smtp_port or (465 if args.ssl else 587)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = args.sender
    message["To"] = ", ".join(args.to)
    message.set_content(body)
    try:
        if args.ssl:
            server = smtplib.SMTP_SSL(args.smtp_host, port,
                                      timeout=args.timeout, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(args.smtp_host, port, timeout=args.timeout)
            server.ehlo()
            if not args.no_tls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
        with server:
            if args.smtp_user:
                server.login(args.smtp_user, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        raise RuntimeError(f"could not send email: {exc}") from exc


def seed_demo(conn: sqlite3.Connection) -> None:
    """Load the complete bundled catalogue into the database."""
    for show in SAMPLE_SHOWS:
        save_show(conn, show, SAMPLE_EPISODES[show["id"]])


def run_demo() -> int:
    """Exercise the offline catalogue, watchlist, schedule, and reminder preview."""
    print("TV Show Tracker — demo (offline bundled catalogue)")
    with tempfile.TemporaryDirectory(prefix="tv-tracker-") as tmp:
        with connect(Path(tmp) / "shows.db") as conn:
            seed_demo(conn)
            print(f"Loaded {len(SAMPLE_SHOWS)} shows and "
                  f"{sum(len(eps) for eps in SAMPLE_EPISODES.values())} episodes\n")
            print("--- WATCHLIST (today = 2026-11-02) ---")
            print(watchlist_text(conn, DEMO_TODAY))
            print("\n--- SEARCH: 'signal' ---")
            print(search_text(search_sample("signal"), "bundled sample"))
            print("\n--- NEXT AIRINGS: 14 days ---")
            print(next_text(conn, 14, DEMO_TODAY))
            print("\n--- SCHEDULE: 2026-11-03 ---")
            print(schedule_text(schedule_sample(date(2026, 11, 3)), date(2026, 11, 3), "bundled sample"))
            print("\n--- MARK 'Kitchen Lab' WATCHED ---")
            set_watched(conn, 9002, True)
            print(watchlist_text(conn, DEMO_TODAY))
            subject, body = build_reminder(conn, 7, DEMO_TODAY)
            print("\n--- EMAIL REMINDER PREVIEW (not sent) ---")
            print(f"Subject: {subject}\n{body}")
            print("\nDemo complete. Network use: python3 solution.py --search 'severance' "
                  "--add ID --watchlist")
        print()
    return 0


def interactive(db_path: Path) -> int:
    with connect(db_path) as conn:
        while True:
            print("\n1) search  2) add by ID  3) watchlist  4) next airings"
                  "  5) episodes  6) mark watched  0) quit")
            choice = input("Choose: ").strip()
            try:
                if choice == "0":
                    return 0
                if choice == "1":
                    query = input("Search: ")
                    try:
                        results = search_api(query)
                        source = "TVmaze"
                    except NetworkError as exc:
                        print(f"network unavailable ({exc}); using bundled sample")
                        results = search_sample(query)
                        source = "bundled sample"
                    print(search_text(results, source))
                elif choice == "2":
                    show_id = int(input("TVmaze show ID: "))
                    add_show_by_id(conn, show_id, offline=False, timeout=6.0)
                elif choice == "3":
                    print(watchlist_text(conn, date.today()))
                elif choice == "4":
                    print(next_text(conn, 14, date.today()))
                elif choice == "5":
                    print(episodes_text(conn, int(input("Show ID: "))))
                elif choice == "6":
                    show_id = int(input("Show ID: "))
                    watched = input("Watched? [y/N]: ").strip().lower().startswith("y")
                    print("Updated." if set_watched(conn, show_id, watched) else "Show not found.")
                else:
                    print("Unknown choice.")
            except (ValueError, sqlite3.Error) as exc:
                print(f"error: {exc}")


def add_show_by_id(conn: sqlite3.Connection, show_id: int, offline: bool,
                   timeout: float) -> bool:
    """Add a show from TVmaze, or the sample catalogue when offline."""
    if not offline:
        try:
            show, episodes = fetch_show_api(show_id, timeout=timeout)
            created = save_show(conn, show, episodes)
            print(f"{'Added' if created else 'Updated'} '{show['name']}' "
                  f"with {len(episodes)} episode(s) from TVmaze.")
            return True
        except NetworkError as exc:
            print(f"network unavailable ({exc}); trying bundled sample", file=sys.stderr)
    sample = sample_show(show_id)
    if not sample:
        print(f"error: show {show_id} is not in the offline sample", file=sys.stderr)
        return False
    show, episodes = sample
    created = save_show(conn, show, episodes)
    print(f"{'Added' if created else 'Updated'} '{show['name']}' with "
          f"{len(episodes)} episode(s) from the bundled sample.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Track TV shows and episodes, with TVmaze lookups, watchlist, and email reminders.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database (default: tvshows.db)")
    parser.add_argument("--search", metavar="TEXT", help="search TVmaze (falls back offline)")
    parser.add_argument("--add", type=int, metavar="ID", help="add a show by TVmaze id")
    parser.add_argument("--remove", type=int, metavar="ID", help="remove a show")
    parser.add_argument("--watch", type=int, metavar="ID", help="mark a show watched")
    parser.add_argument("--unwatch", type=int, metavar="ID", help="mark a show unwatched")
    parser.add_argument("--watchlist", action="store_true", help="list unwatched shows")
    parser.add_argument("--all", action="store_true", help="list every stored show")
    parser.add_argument("--episodes", type=int, metavar="ID", help="list episodes for a show")
    parser.add_argument("--next", nargs="?", const=14, type=int, metavar="DAYS",
                        help="next airings for the watchlist (default 14 days)")
    parser.add_argument("--schedule", nargs="?", const="today", metavar="YYYY-MM-DD",
                        help="broadcast schedule for a date (default today)")
    parser.add_argument("--remind", action="store_true", help="build/send the reminder email")
    parser.add_argument("--days", type=int, default=7, help="reminder horizon in days")
    parser.add_argument("--offline", action="store_true", help="never use the network")
    parser.add_argument("--country", default="US", help="country code for --schedule")
    parser.add_argument("--timeout", type=float, default=6.0, help="network timeout in seconds")
    parser.add_argument("--smtp-host", help="SMTP server for reminders")
    parser.add_argument("--smtp-port", type=int, default=0,
                        help="SMTP port (default 587, or 465 with --ssl)")
    parser.add_argument("--smtp-user", help="SMTP user name")
    parser.add_argument("--password-env", default="SMTP_PASSWORD",
                        help="environment variable holding the SMTP password")
    parser.add_argument("--from", dest="sender", help="sender address")
    parser.add_argument("--to", action="append", default=[], help="recipient (repeatable)")
    parser.add_argument("--ssl", action="store_true", help="use implicit TLS (port 465)")
    parser.add_argument("--no-tls", action="store_true", help="do not STARTTLS")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if len(sys.argv) == 1 and argv is None:
        return interactive(args.db)

    try:
        with connect(args.db) as conn:
            if args.search is not None:
                if args.offline:
                    results, source = search_sample(args.search), "bundled sample"
                else:
                    try:
                        results, source = search_api(args.search, timeout=args.timeout), "TVmaze"
                    except NetworkError as exc:
                        print(f"network unavailable ({exc}); using bundled sample", file=sys.stderr)
                        results, source = search_sample(args.search), "bundled sample"
                print(search_text(results, source))
                return 0
            if args.add is not None:
                return 0 if add_show_by_id(conn, args.add, args.offline, args.timeout) else 2
            if args.remove is not None:
                if remove_show(conn, args.remove):
                    print(f"Removed show {args.remove}.")
                    return 0
                print(f"error: show {args.remove} not found", file=sys.stderr)
                return 2
            if args.watch is not None or args.unwatch is not None:
                show_id = args.watch if args.watch is not None else args.unwatch
                if set_watched(conn, show_id, args.watch is not None):
                    print(f"Marked show {show_id} as {'watched' if args.watch is not None else 'unwatched'}.")
                    return 0
                print(f"error: show {show_id} not found", file=sys.stderr)
                return 2
            if args.all:
                print(list_shows_text(conn))
                return 0
            if args.watchlist:
                print(watchlist_text(conn, date.today()))
                return 0
            if args.episodes is not None:
                print(episodes_text(conn, args.episodes))
                return 0
            if args.next is not None:
                print(next_text(conn, args.next, date.today()))
                return 0
            if args.schedule is not None:
                day = date.today() if args.schedule == "today" else date.fromisoformat(args.schedule)
                entries, source = [], "bundled sample"
                if not args.offline:
                    try:
                        entries, source = schedule_api(day, args.country, timeout=args.timeout), "TVmaze"
                    except NetworkError as exc:
                        print(f"network unavailable ({exc}); using bundled sample", file=sys.stderr)
                if source == "bundled sample":
                    entries = schedule_sample(day)
                print(schedule_text(entries, day, source))
                return 0
            if args.remind:
                subject, body = build_reminder(conn, args.days, date.today())
                if not args.smtp_host:
                    print("SMTP not configured; reminder preview only:\n")
                    print(f"Subject: {subject}\n\n{body}")
                    return 0
                send_email(subject, body, args)
                print(f"Sent reminder to {', '.join(args.to)}.")
                return 0
            parser.print_help()
            return 0
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
