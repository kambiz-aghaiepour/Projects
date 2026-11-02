#!/usr/bin/env python3
"""Travel Planner System: trips, flights, hotels, POIs, budget and itinerary.

A SQLite-backed planner.  Each trip owns flights, hotel stays, points of
interest, and budget lines.  The program prints a day-by-day itinerary, checks
for scheduling problems (overlapping flights/hotels/POIs, uncovered nights,
items outside the trip, budget overruns), and imports/exports everything as
JSON for backup or sharing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("travel.db")
DT_FORMAT = "%Y-%m-%d %H:%M"
SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    airline TEXT NOT NULL,
    flight_no TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart_ts TEXT NOT NULL,
    arrive_ts TEXT NOT NULL,
    confirmation TEXT NOT NULL DEFAULT '',
    cost_cents INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hotels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    checkin_date TEXT NOT NULL,
    checkout_date TEXT NOT NULL,
    confirmation TEXT NOT NULL DEFAULT '',
    cost_cents INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'sightseeing',
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    cost_cents INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flights_trip ON flights(trip_id);
CREATE INDEX IF NOT EXISTS idx_hotels_trip ON hotels(trip_id);
CREATE INDEX IF NOT EXISTS idx_pois_trip ON pois(trip_id);
"""


@dataclass
class Conflict:
    severity: str
    message: str


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def parse_date(text: str, label: str = "date") -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got '{text}'") from exc


def parse_datetime(text: str, label: str = "datetime") -> datetime:
    cleaned = text.strip().replace("T", " ")
    try:
        return datetime.strptime(cleaned, DT_FORMAT)
    except ValueError as exc:
        raise ValueError(f"{label} must be 'YYYY-MM-DD HH:MM', got '{text}'") from exc


def parse_clock(text: str, label: str = "time") -> time:
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"{label} must be HH:MM, got '{text}'") from exc


def parse_money(text: str, label: str = "amount") -> int:
    cleaned = str(text).replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label} '{text}'") from exc
    if not value.is_finite():
        raise ValueError(f"invalid {label} '{text}'")
    if value < 0:
        raise ValueError(f"{label} must not be negative")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def get_trip(conn: sqlite3.Connection, trip_id: int) -> sqlite3.Row:
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        raise ValueError(f"trip #{trip_id} not found")
    return trip


def add_trip(conn: sqlite3.Connection, name: str, destination: str, start: date,
             end: date, notes: str = "", currency: str = "USD") -> int:
    if not name.strip() or not destination.strip():
        raise ValueError("trip name and destination must not be empty")
    if end < start:
        raise ValueError("trip end date must be on or after the start date")
    cursor = conn.execute(
        "INSERT INTO trips(name, destination, start_date, end_date, notes, currency) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name.strip(), destination.strip(), start.isoformat(), end.isoformat(),
         notes.strip(), currency.strip().upper() or "USD"),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def add_flight(conn: sqlite3.Connection, trip_id: int, airline: str, flight_no: str,
               origin: str, destination: str, depart: datetime, arrive: datetime,
               confirmation: str = "", cost_cents: int = 0) -> int:
    get_trip(conn, trip_id)
    if arrive <= depart:
        raise ValueError("flight arrival must be after departure")
    if not all(value.strip() for value in (airline, flight_no, origin, destination)):
        raise ValueError("airline, flight number, origin, and destination are required")
    cursor = conn.execute(
        """INSERT INTO flights(trip_id, airline, flight_no, origin, destination,
                               depart_ts, arrive_ts, confirmation, cost_cents)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, airline.strip(), flight_no.strip(), origin.strip().upper(),
         destination.strip().upper(), depart.strftime(DT_FORMAT),
         arrive.strftime(DT_FORMAT), confirmation.strip(), cost_cents),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def add_hotel(conn: sqlite3.Connection, trip_id: int, name: str, city: str,
              checkin: date, checkout: date, confirmation: str = "",
              cost_cents: int = 0) -> int:
    get_trip(conn, trip_id)
    if checkout <= checkin:
        raise ValueError("hotel checkout must be after check-in")
    if not name.strip() or not city.strip():
        raise ValueError("hotel name and city are required")
    cursor = conn.execute(
        """INSERT INTO hotels(trip_id, name, city, checkin_date, checkout_date,
                              confirmation, cost_cents)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, name.strip(), city.strip(), checkin.isoformat(), checkout.isoformat(),
         confirmation.strip(), cost_cents),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def add_poi(conn: sqlite3.Connection, trip_id: int, name: str, day: date,
            start: time, end: time, category: str = "sightseeing",
            notes: str = "", cost_cents: int = 0) -> int:
    get_trip(conn, trip_id)
    if end <= start:
        raise ValueError("POI end time must be after start time")
    if not name.strip():
        raise ValueError("POI name must not be empty")
    cursor = conn.execute(
        """INSERT INTO pois(trip_id, name, category, date, start_time, end_time,
                            notes, cost_cents)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, name.strip(), category.strip() or "sightseeing", day.isoformat(),
         start.strftime("%H:%M"), end.strftime("%H:%M"), notes.strip(), cost_cents),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def add_budget_item(conn: sqlite3.Connection, trip_id: int, category: str,
                    description: str, amount_cents: int) -> int:
    get_trip(conn, trip_id)
    if amount_cents < 0:
        raise ValueError("budget amount must not be negative")
    if not category.strip():
        raise ValueError("budget category must not be empty")
    cursor = conn.execute(
        "INSERT INTO budget_items(trip_id, category, description, amount_cents) "
        "VALUES (?, ?, ?, ?)",
        (trip_id, category.strip(), description.strip(), amount_cents),
    )
    conn.commit()
    return int(cursor.lastrowid or 0)


def flight_rows(conn: sqlite3.Connection, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM flights WHERE trip_id = ? ORDER BY depart_ts", (trip_id,)
    ).fetchall()


def hotel_rows(conn: sqlite3.Connection, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM hotels WHERE trip_id = ? ORDER BY checkin_date", (trip_id,)
    ).fetchall()


def poi_rows(conn: sqlite3.Connection, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pois WHERE trip_id = ? ORDER BY date, start_time", (trip_id,)
    ).fetchall()


def budget_rows(conn: sqlite3.Connection, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM budget_items WHERE trip_id = ? ORDER BY category, id", (trip_id,)
    ).fetchall()


def trip_totals(conn: sqlite3.Connection, trip_id: int) -> dict[str, int]:
    flights = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_cents), 0) FROM flights WHERE trip_id = ?",
        (trip_id,)).fetchone()
    hotels = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_cents), 0) FROM hotels WHERE trip_id = ?",
        (trip_id,)).fetchone()
    pois = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_cents), 0) FROM pois WHERE trip_id = ?",
        (trip_id,)).fetchone()
    budget = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0), COUNT(*) FROM budget_items WHERE trip_id = ?",
        (trip_id,)).fetchone()
    nights = sum((date.fromisoformat(row["checkout_date"]) - date.fromisoformat(row["checkin_date"])).days
                 for row in hotel_rows(conn, trip_id))
    planned = int(flights[1]) + int(hotels[1]) + int(pois[1])
    return {
        "flights": int(flights[0]), "flight_cost": int(flights[1]),
        "hotels": int(hotels[0]), "hotel_cost": int(hotels[1]), "nights": nights,
        "pois": int(pois[0]), "poi_cost": int(pois[1]),
        "budget_count": int(budget[1]), "budget_total": int(budget[0]),
        "planned": planned,
    }


def trips_text(conn: sqlite3.Connection) -> str:
    trips = conn.execute("SELECT * FROM trips ORDER BY start_date, id").fetchall()
    if not trips:
        return "No trips yet. Create one with --add-trip."
    lines = [f"Trips ({len(trips)}):",
             f"{'ID':>3}  {'Name':28}  {'Destination':18}  {'Dates':25}  Planned"]
    for trip in trips:
        totals = trip_totals(conn, int(trip["id"]))
        lines.append(f"{trip['id']:>3}  {trip['name'][:28]:28}  {trip['destination'][:18]:18}  "
                     f"{trip['start_date']} to {trip['end_date']}  {money(totals['planned'])}")
    return "\n".join(lines)


def trip_dates(trip: sqlite3.Row) -> list[date]:
    start = date.fromisoformat(trip["start_date"])
    end = date.fromisoformat(trip["end_date"])
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def itinerary_text(conn: sqlite3.Connection, trip_id: int) -> str:
    """Render the day-by-day itinerary and cost summary for a trip."""
    trip = get_trip(conn, trip_id)
    flights = flight_rows(conn, trip_id)
    hotels = hotel_rows(conn, trip_id)
    pois = poi_rows(conn, trip_id)
    totals = trip_totals(conn, trip_id)
    lines = [
        "=" * 82,
        f"{trip['name']} — {trip['destination']}",
        f"{trip['start_date']} to {trip['end_date']}  ·  {len(trip_dates(trip))} day(s)  ·  {trip['currency']}",
    ]
    if trip["notes"]:
        lines.append(trip["notes"])
    lines.append("=" * 82)
    for day in trip_dates(trip):
        day_iso = day.isoformat()
        lines.append(f"\n{day.strftime('%A, %B %d, %Y')}")
        entries = []
        for flight in flights:
            depart = datetime.strptime(flight["depart_ts"], DT_FORMAT)
            arrive = datetime.strptime(flight["arrive_ts"], DT_FORMAT)
            if depart.date() == day:
                extra_days = (arrive.date() - depart.date()).days
                next_day = f" (+{extra_days})" if extra_days else ""
                entries.append((depart.time(), f"✈ {flight['airline']} {flight['flight_no']}  "
                                f"{flight['origin']} {depart:%H:%M} → {flight['destination']} "
                                f"{arrive:%H:%M}{next_day}  {money(int(flight['cost_cents']))}"))
            elif arrive.date() == day and depart.date() != day:
                entries.append((arrive.time(), f"✈ Arrive {flight['airline']} {flight['flight_no']} "
                                f"at {flight['destination']} {arrive:%H:%M}"))
        for hotel in hotels:
            checkin = date.fromisoformat(hotel["checkin_date"])
            checkout = date.fromisoformat(hotel["checkout_date"])
            if checkin <= day <= checkout:
                if day == checkin:
                    label = f"Check in: {hotel['name']} ({hotel['city']})"
                    if hotel["confirmation"]:
                        label += f"  conf {hotel['confirmation']}"
                    entries.append((time(15, 0), f"🏨 {label}  {money(int(hotel['cost_cents']))}"))
                elif day == checkout:
                    entries.append((time(11, 0), f"🏨 Check out: {hotel['name']}"))
                else:
                    entries.append((time(8, 0), f"🏨 Staying at {hotel['name']} ({hotel['city']})"))
        for poi in pois:
            if poi["date"] == day_iso:
                cost = f"  {money(int(poi['cost_cents']))}" if poi["cost_cents"] else ""
                entries.append((parse_clock(poi["start_time"]),
                                f"• {poi['start_time']}-{poi['end_time']}  {poi['name']} "
                                f"[{poi['category']}]{cost}"))
                if poi["notes"]:
                    entries.append((parse_clock(poi["start_time"]), f"    {poi['notes']}"))
        if not entries:
            lines.append("  (no activities planned)")
        else:
            for _, text in sorted(entries, key=lambda item: item[0]):
                lines.append("  " + text)

    lines.append("\n" + "-" * 82)
    lines.append("COST SUMMARY")
    lines.append(f"  Flights: {totals['flights']} · {money(totals['flight_cost'])}")
    lines.append(f"  Hotels:  {totals['hotels']} stay(s), {totals['nights']} night(s) · "
                 f"{money(totals['hotel_cost'])}")
    lines.append(f"  POIs:    {totals['pois']} · {money(totals['poi_cost'])}")
    lines.append(f"  Planned total: {money(totals['planned'])}")
    if totals["budget_count"]:
        remaining = totals["budget_total"] - totals["planned"]
        lines.append(f"  Budget:  {money(totals['budget_total'])}  ·  "
                     f"{'Remaining' if remaining >= 0 else 'Over'} {money(abs(remaining))}")
        lines.append("  Budget lines:")
        for item in budget_rows(conn, trip_id):
            lines.append(f"    - {item['category']}: {money(int(item['amount_cents']))}"
                         f"  {item['description']}")
    else:
        lines.append("  Budget: not set")
    return "\n".join(lines)


def find_conflicts(conn: sqlite3.Connection, trip_id: int) -> list[Conflict]:
    """Check intervals, coverage, trip bounds, and budget."""
    trip = get_trip(conn, trip_id)
    start = date.fromisoformat(trip["start_date"])
    end = date.fromisoformat(trip["end_date"])
    conflicts: list[Conflict] = []
    flights = flight_rows(conn, trip_id)
    hotels = hotel_rows(conn, trip_id)
    pois = poi_rows(conn, trip_id)

    flight_times = [(row, datetime.strptime(row["depart_ts"], DT_FORMAT),
                     datetime.strptime(row["arrive_ts"], DT_FORMAT)) for row in flights]
    for index, (row_a, depart_a, arrive_a) in enumerate(flight_times):
        for row_b, depart_b, arrive_b in flight_times[index + 1:]:
            if depart_a < arrive_b and arrive_a > depart_b:
                conflicts.append(Conflict("ERROR", f"Flights {row_a['flight_no']} and "
                                          f"{row_b['flight_no']} overlap in time"))
        if depart_a.date() < start:
            conflicts.append(Conflict("WARNING", f"Flight {row_a['flight_no']} departs before the trip starts"))
        if arrive_a.date() > end:
            conflicts.append(Conflict("WARNING", f"Flight {row_a['flight_no']} arrives after the trip ends"))

    for index, hotel_a in enumerate(hotels):
        checkin_a = date.fromisoformat(hotel_a["checkin_date"])
        checkout_a = date.fromisoformat(hotel_a["checkout_date"])
        for hotel_b in hotels[index + 1:]:
            checkin_b = date.fromisoformat(hotel_b["checkin_date"])
            checkout_b = date.fromisoformat(hotel_b["checkout_date"])
            if checkin_a < checkout_b and checkout_a > checkin_b:
                conflicts.append(Conflict("ERROR", f"Hotels '{hotel_a['name']}' and "
                                          f"'{hotel_b['name']}' overlap"))
        if checkin_a < start or checkout_a > end:
            conflicts.append(Conflict("WARNING", f"Hotel '{hotel_a['name']}' extends outside the trip dates"))

    for index, poi_a in enumerate(pois):
        day_a = date.fromisoformat(poi_a["date"])
        start_a = datetime.combine(day_a, parse_clock(poi_a["start_time"]))
        end_a = datetime.combine(day_a, parse_clock(poi_a["end_time"]))
        if day_a < start or day_a > end:
            conflicts.append(Conflict("WARNING", f"POI '{poi_a['name']}' is outside the trip dates"))
        for poi_b in pois[index + 1:]:
            day_b = date.fromisoformat(poi_b["date"])
            if day_a != day_b:
                continue
            start_b = datetime.combine(day_b, parse_clock(poi_b["start_time"]))
            end_b = datetime.combine(day_b, parse_clock(poi_b["end_time"]))
            if start_a < end_b and end_a > start_b:
                conflicts.append(Conflict("WARNING", f"POIs '{poi_a['name']}' and "
                                          f"'{poi_b['name']}' overlap on {day_a.isoformat()}"))

    covered: set[date] = set()
    for hotel in hotels:
        checkin = date.fromisoformat(hotel["checkin_date"])
        checkout = date.fromisoformat(hotel["checkout_date"])
        day = checkin
        while day < checkout:
            covered.add(day)
            day += timedelta(days=1)
    missing = [day for day in (start + timedelta(days=offset)
                               for offset in range(max(0, (end - start).days)))
               if day not in covered]
    if missing:
        groups: list[tuple[date, date]] = []
        for day in missing:
            if groups and day == groups[-1][1] + timedelta(days=1):
                groups[-1] = (groups[-1][0], day)
            else:
                groups.append((day, day))
        for first, last in groups:
            label = first.isoformat() if first == last else f"{first.isoformat()} to {last.isoformat()}"
            conflicts.append(Conflict("WARNING", f"No hotel booked for {label}"))

    totals = trip_totals(conn, trip_id)
    if totals["budget_count"]:
        if totals["planned"] > totals["budget_total"]:
            conflicts.append(Conflict("WARNING", f"Planned costs exceed the budget by "
                                      f"{money(totals['planned'] - totals['budget_total'])}"))
    elif totals["planned"]:
        conflicts.append(Conflict("INFO", "No budget has been recorded for this trip"))

    return conflicts


def conflicts_text(conn: sqlite3.Connection, trip_id: int) -> str:
    trip = get_trip(conn, trip_id)
    conflicts = find_conflicts(conn, trip_id)
    lines = [f"Conflict check for '{trip['name']}':"]
    if not conflicts:
        lines.append("  No conflicts detected.")
        return "\n".join(lines)
    for conflict in conflicts:
        lines.append(f"  [{conflict.severity:<7}] {conflict.message}")
    errors = sum(1 for item in conflicts if item.severity == "ERROR")
    warnings = sum(1 for item in conflicts if item.severity == "WARNING")
    lines.append(f"\n{errors} error(s), {warnings} warning(s).")
    return "\n".join(lines)


def export_json(conn: sqlite3.Connection, path: Path, trip_id: int | None = None) -> tuple[int, int]:
    """Export trips (all or one) to JSON; return trip and item counts."""
    if trip_id is not None:
        get_trip(conn, trip_id)
        trips = [conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()]
    else:
        trips = conn.execute("SELECT * FROM trips ORDER BY id").fetchall()
    payload: dict[str, Any] = {
        "format": "travel-planner",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trips": [],
    }
    item_count = 0
    for trip in trips:
        children = {
            "flights": [dict(row) for row in flight_rows(conn, int(trip["id"]))],
            "hotels": [dict(row) for row in hotel_rows(conn, int(trip["id"]))],
            "pois": [dict(row) for row in poi_rows(conn, int(trip["id"]))],
            "budget_items": [dict(row) for row in budget_rows(conn, int(trip["id"]))],
        }
        for rows in children.values():
            for row in rows:
                row.pop("id", None)
                row.pop("trip_id", None)
        trip_dict = {key: trip[key] for key in trip.keys() if key != "id"}
        trip_dict.update(children)
        payload["trips"].append(trip_dict)
        item_count += sum(len(rows) for rows in children.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(trips), item_count


def import_json(conn: sqlite3.Connection, path: Path) -> tuple[int, int]:
    """Import a JSON export, validating each trip before writing."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("trips"), list):
        raise ValueError("JSON must be an object with a 'trips' array")

    prepared = []
    for index, raw in enumerate(payload["trips"], start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"trip {index} is not an object")
        try:
            start = parse_date(str(raw["start_date"]), "start_date")
            end = parse_date(str(raw["end_date"]), "end_date")
            if end < start:
                raise ValueError("end_date is before start_date")
            for flight in raw.get("flights", []):
                depart = parse_datetime(str(flight["depart_ts"]), "depart_ts")
                arrive = parse_datetime(str(flight["arrive_ts"]), "arrive_ts")
                if arrive <= depart:
                    raise ValueError("flight arrives before it departs")
            for hotel in raw.get("hotels", []):
                if parse_date(str(hotel["checkout_date"])) <= parse_date(str(hotel["checkin_date"])):
                    raise ValueError("hotel checkout is before check-in")
            for poi in raw.get("pois", []):
                if parse_clock(str(poi["end_time"])) <= parse_clock(str(poi["start_time"])):
                    raise ValueError("POI end time is before start time")
        except (KeyError, ValueError) as exc:
            raise ValueError(f"trip {index}: {exc}") from exc
        prepared.append(raw)

    trip_count = 0
    item_count = 0
    for raw in prepared:
        trip_id = add_trip(conn, str(raw["name"]), str(raw["destination"]),
                           parse_date(str(raw["start_date"])), parse_date(str(raw["end_date"])),
                           str(raw.get("notes", "")), str(raw.get("currency", "USD")))
        trip_count += 1
        for flight in raw.get("flights", []):
            add_flight(conn, trip_id, str(flight.get("airline", "")),
                       str(flight.get("flight_no", "")), str(flight.get("origin", "")),
                       str(flight.get("destination", "")),
                       parse_datetime(str(flight["depart_ts"])),
                       parse_datetime(str(flight["arrive_ts"])),
                       str(flight.get("confirmation", "")),
                       int(flight.get("cost_cents", 0)))
            item_count += 1
        for hotel in raw.get("hotels", []):
            add_hotel(conn, trip_id, str(hotel.get("name", "")), str(hotel.get("city", "")),
                      parse_date(str(hotel["checkin_date"])), parse_date(str(hotel["checkout_date"])),
                      str(hotel.get("confirmation", "")), int(hotel.get("cost_cents", 0)))
            item_count += 1
        for poi in raw.get("pois", []):
            add_poi(conn, trip_id, str(poi.get("name", "")), parse_date(str(poi["date"])),
                    parse_clock(str(poi["start_time"])), parse_clock(str(poi["end_time"])),
                    str(poi.get("category", "sightseeing")), str(poi.get("notes", "")),
                    int(poi.get("cost_cents", 0)))
            item_count += 1
        for item in raw.get("budget_items", []):
            add_budget_item(conn, trip_id, str(item.get("category", "other")),
                            str(item.get("description", "")), int(item.get("amount_cents", 0)))
            item_count += 1
    conn.commit()
    return trip_count, item_count


def seed_demo(conn: sqlite3.Connection) -> int:
    """Create a Kyoto/Osaka trip with a deliberate POI overlap."""
    trip_id = add_trip(conn, "Kyoto & Osaka Spring", "Japan", date(2026, 4, 10),
                       date(2026, 4, 15),
                       "Cherry blossoms, temples, and food markets. JR Pass loaded.",
                       "USD")
    add_flight(conn, trip_id, "Pacific Air", "PA 118", "SFO", "KIX",
               datetime(2026, 4, 10, 9, 0), datetime(2026, 4, 10, 13, 0),
               "PA118-X7K2", 95_000)
    add_flight(conn, trip_id, "Pacific Air", "PA 119", "KIX", "SFO",
               datetime(2026, 4, 15, 16, 0), datetime(2026, 4, 15, 20, 0),
               "PA119-Q3M8", 95_000)
    add_hotel(conn, trip_id, "Kyoto Ryokan", "Kyoto", date(2026, 4, 10),
              date(2026, 4, 13), "RYO-4412", 72_000)
    add_hotel(conn, trip_id, "Osaka Harbor Hotel", "Osaka", date(2026, 4, 13),
              date(2026, 4, 15), "OHH-9081", 54_000)
    add_poi(conn, trip_id, "Fushimi Inari Shrine", date(2026, 4, 11),
            time(9, 0), time(11, 0), "sightseeing",
            "Walk the torii gate path before the crowds.", 0)
    add_poi(conn, trip_id, "Tea ceremony", date(2026, 4, 11),
            time(10, 30), time(11, 30), "culture",
            "Reserved at Camellia Tea House.", 6_000)
    add_poi(conn, trip_id, "Arashiyama Bamboo Grove", date(2026, 4, 12),
            time(9, 30), time(12, 0), "nature", "Bamboo grove and riverside walk.", 0)
    add_poi(conn, trip_id, "Osaka Castle", date(2026, 4, 14),
            time(10, 0), time(12, 0), "sightseeing", "Museum and main tower.", 1_200)
    add_poi(conn, trip_id, "Dotonbori food crawl", date(2026, 4, 14),
            time(18, 0), time(20, 0), "food", "Takoyaki, okonomiyaki, and taiyaki.", 4_500)
    for category, description, amount in (
        ("transport", "Flights", 190_000), ("lodging", "Hotels", 126_000),
        ("food", "Meals and markets", 40_000), ("activities", "Temples and tours", 20_000),
    ):
        add_budget_item(conn, trip_id, category, description, amount)
    return trip_id


def run_demo() -> int:
    """Build a sample trip, print itinerary/conflicts, and round-trip JSON."""
    print("Travel Planner System — demo")
    with tempfile.TemporaryDirectory(prefix="travel-planner-") as tmp:
        db_path = Path(tmp) / "travel.db"
        with connect(db_path) as conn:
            trip_id = seed_demo(conn)
            print("Created a 6-day Kyoto/Osaka trip with flights, 2 hotels, 5 POIs, and a budget\n")
            print(itinerary_text(conn, trip_id))
            print("\n" + "=" * 82)
            print(conflicts_text(conn, trip_id))

            json_path = Path(tmp) / "trip.json"
            trips, items = export_json(conn, json_path, trip_id)
            print(f"\nExported {trips} trip and {items} items to JSON ({json_path.stat().st_size:,} bytes)")

            second_path = Path(tmp) / "imported.db"
            with connect(second_path) as second:
                imported_trips, imported_items = import_json(second, json_path)
                original_totals = trip_totals(conn, trip_id)
                copied_totals = trip_totals(second, 1)
                print(f"Imported {imported_trips} trip and {imported_items} items into a fresh database")
                print(f"Round-trip totals match: {original_totals['planned'] == copied_totals['planned']}"
                      f" (planned {money(copied_totals['planned'])}, "
                      f"{copied_totals['nights']} hotel nights)")
        print("\nDemo complete. Real use: python3 solution.py --db travel.db --trips")
    return 0


def interactive(db_path: Path) -> int:
    with connect(db_path) as conn:
        while True:
            print("\n1) trips  2) add trip  3) add flight  4) add hotel  5) add POI"
                  "  6) itinerary  7) conflicts  8) export JSON  0) quit")
            choice = input("Choose: ").strip()
            try:
                if choice == "0":
                    return 0
                if choice == "1":
                    print(trips_text(conn))
                elif choice == "2":
                    trip_id = add_trip(
                        conn, input("Trip name: "), input("Destination: "),
                        parse_date(input("Start (YYYY-MM-DD): ")),
                        parse_date(input("End (YYYY-MM-DD): ")),
                        input("Notes: "), input("Currency [USD]: ") or "USD")
                    print(f"Created trip #{trip_id}.")
                elif choice == "3":
                    trip_id = int(input("Trip ID: "))
                    add_flight(conn, trip_id, input("Airline: "), input("Flight number: "),
                               input("From: "), input("To: "),
                               parse_datetime(input("Depart (YYYY-MM-DD HH:MM): ")),
                               parse_datetime(input("Arrive (YYYY-MM-DD HH:MM): ")),
                               input("Confirmation: "),
                               parse_money(input("Cost [$0]: ") or "0"))
                    print("Flight added.")
                elif choice == "4":
                    trip_id = int(input("Trip ID: "))
                    add_hotel(conn, trip_id, input("Hotel name: "), input("City: "),
                              parse_date(input("Check-in (YYYY-MM-DD): ")),
                              parse_date(input("Check-out (YYYY-MM-DD): ")),
                              input("Confirmation: "),
                              parse_money(input("Cost [$0]: ") or "0"))
                    print("Hotel added.")
                elif choice == "5":
                    trip_id = int(input("Trip ID: "))
                    add_poi(conn, trip_id, input("POI name: "),
                            parse_date(input("Date (YYYY-MM-DD): ")),
                            parse_clock(input("Start (HH:MM): ")),
                            parse_clock(input("End (HH:MM): ")),
                            input("Category [sightseeing]: ") or "sightseeing",
                            input("Notes: "), parse_money(input("Cost [$0]: ") or "0"))
                    print("POI added.")
                elif choice == "6":
                    print(itinerary_text(conn, int(input("Trip ID: "))))
                elif choice == "7":
                    print(conflicts_text(conn, int(input("Trip ID: "))))
                elif choice == "8":
                    path = Path(input("JSON path [trips.json]: ") or "trips.json")
                    trips, items = export_json(conn, path)
                    print(f"Exported {trips} trip(s) and {items} item(s).")
                else:
                    print("Unknown choice.")
            except (ValueError, sqlite3.Error, OSError) as exc:
                print(f"error: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solution.py",
        description="Plan trips with flights, hotels, POIs, budgets, itineraries, and conflict checks.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database (default: travel.db)")
    parser.add_argument("--add-trip", action="store_true", help="create a trip")
    parser.add_argument("--name", help="trip, hotel, or POI name")
    parser.add_argument("--destination", help="trip destination (or flight destination)")
    parser.add_argument("--start", metavar="YYYY-MM-DD", help="trip start date")
    parser.add_argument("--end", metavar="YYYY-MM-DD", help="trip end date")
    parser.add_argument("--notes", default="", help="trip or POI notes")
    parser.add_argument("--currency", default="USD", help="trip currency code")
    parser.add_argument("--add-flight", action="store_true", help="add a flight")
    parser.add_argument("--trip", type=int, metavar="ID", help="trip id for add/export commands")
    parser.add_argument("--airline", help="airline name")
    parser.add_argument("--flight-no", help="flight number")
    parser.add_argument("--from", dest="origin", help="flight origin airport code")
    parser.add_argument("--to", dest="arrive_at", help="flight destination airport code")
    parser.add_argument("--depart", metavar="'YYYY-MM-DD HH:MM'", help="flight departure")
    parser.add_argument("--arrive", metavar="'YYYY-MM-DD HH:MM'", help="flight arrival")
    parser.add_argument("--confirmation", default="", help="booking confirmation code")
    parser.add_argument("--cost", default="0", help="item cost in dollars (default 0)")
    parser.add_argument("--add-hotel", action="store_true", help="add a hotel stay")
    parser.add_argument("--city", help="hotel city")
    parser.add_argument("--checkin", metavar="YYYY-MM-DD", help="hotel check-in")
    parser.add_argument("--checkout", metavar="YYYY-MM-DD", help="hotel check-out")
    parser.add_argument("--add-poi", action="store_true", help="add a point of interest")
    parser.add_argument("--date", help="POI date YYYY-MM-DD")
    parser.add_argument("--start-time", help="POI start time HH:MM")
    parser.add_argument("--end-time", help="POI end time HH:MM")
    parser.add_argument("--category", help="POI or budget category")
    parser.add_argument("--add-budget", action="store_true", help="add a budget line")
    parser.add_argument("--description", default="", help="budget line description")
    parser.add_argument("--amount", help="budget amount in dollars")
    parser.add_argument("--trips", action="store_true", help="list trips")
    parser.add_argument("--itinerary", type=int, metavar="ID", help="print a day-by-day itinerary")
    parser.add_argument("--conflicts", type=int, metavar="ID", help="check a trip for conflicts")
    parser.add_argument("--export-json", type=Path, metavar="FILE", help="export all trips (or --trip ID)")
    parser.add_argument("--import-json", type=Path, metavar="FILE", help="import trips from JSON")
    parser.add_argument("--demo", action="store_true", help="run the scripted Kyoto/Osaka demo")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()
    if len(sys.argv) == 1 and argv is None:
        return interactive(args.db)

    try:
        with connect(args.db) as conn:
            if args.add_trip:
                if not args.name or not args.destination or not args.start or not args.end:
                    parser.error("--add-trip requires --name, --destination, --start, and --end")
                trip_id = add_trip(conn, args.name, args.destination,
                                   parse_date(args.start, "--start"), parse_date(args.end, "--end"),
                                   args.notes, args.currency)
                print(f"Created trip #{trip_id}.")
                return 0
            if args.add_flight:
                if not args.trip:
                    parser.error("--add-flight requires --trip")
                if not all((args.airline, args.flight_no, args.origin, args.arrive_at,
                            args.depart, args.arrive)):
                    parser.error("--add-flight requires --airline, --flight-no, --from, --to, "
                                 "--depart, and --arrive")
                flight_id = add_flight(
                    conn, args.trip, args.airline, args.flight_no, args.origin,
                    args.arrive_at, parse_datetime(args.depart, "--depart"),
                    parse_datetime(args.arrive, "--arrive"), args.confirmation,
                    parse_money(args.cost, "cost"),
                )
                print(f"Added flight #{flight_id}.")
                return 0
            if args.add_hotel:
                if not args.trip:
                    parser.error("--add-hotel requires --trip")
                if not args.name or not args.city or not args.checkin or not args.checkout:
                    parser.error("--add-hotel requires --name, --city, --checkin, and --checkout")
                hotel_id = add_hotel(
                    conn, args.trip, args.name, args.city, parse_date(args.checkin, "--checkin"),
                    parse_date(args.checkout, "--checkout"), args.confirmation,
                    parse_money(args.cost, "cost"),
                )
                print(f"Added hotel #{hotel_id}.")
                return 0
            if args.add_poi:
                if not args.trip:
                    parser.error("--add-poi requires --trip")
                if not args.name or not args.date or not args.start_time or not args.end_time:
                    parser.error("--add-poi requires --name, --date, --start-time, and --end-time")
                poi_id = add_poi(
                    conn, args.trip, args.name, parse_date(args.date, "--date"),
                    parse_clock(args.start_time, "--start-time"),
                    parse_clock(args.end_time, "--end-time"), args.category or "sightseeing",
                    args.notes, parse_money(args.cost, "cost"),
                )
                print(f"Added POI #{poi_id}.")
                return 0
            if args.add_budget:
                if not args.trip:
                    parser.error("--add-budget requires --trip")
                if not args.category or not args.amount:
                    parser.error("--add-budget requires --category and --amount")
                budget_id = add_budget_item(conn, args.trip, args.category, args.description,
                                            parse_money(args.amount, "amount"))
                print(f"Added budget line #{budget_id}.")
                return 0
            if args.trips:
                print(trips_text(conn))
                return 0
            if args.itinerary is not None:
                print(itinerary_text(conn, args.itinerary))
                return 0
            if args.conflicts is not None:
                print(conflicts_text(conn, args.conflicts))
                return 0
            if args.export_json:
                trips, items = export_json(conn, args.export_json, args.trip)
                print(f"Exported {trips} trip(s) and {items} item(s) to {args.export_json}.")
                return 0
            if args.import_json:
                trips, items = import_json(conn, args.import_json)
                print(f"Imported {trips} trip(s) and {items} item(s) from {args.import_json}.")
                return 0
            parser.print_help()
            return 0
    except (ValueError, sqlite3.Error, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
