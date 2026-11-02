# Travel Planner System

> Category: `Databases` · Project: `Travel-Planner-System`

## Problem

Make a system that allows users to put together their own travel itinerary and
keep track of airline / hotel arrangements, points of interest, budget and
schedule.

## Features

- Trips with destination, dates, notes, and currency.
- Flights with airline, flight number, route, departure/arrival datetimes,
  confirmation code, and cost.
- Hotel stays with city, check-in/check-out dates, confirmation, and cost.
- Points of interest with date, start/end time, category, notes, and optional
  cost.
- Budget lines by category (transport, lodging, food, activities, …).
- Day-by-day itinerary: flights (including next-day arrivals), hotel check-in /
  stay / check-out, POIs in time order, notes, and per-day cost highlights.
- Cost summary with planned total, budget total, and remaining/over amount.
- Conflict checks:
  - overlapping flights (error),
  - overlapping hotel stays (error),
  - overlapping POIs on the same day (warning),
  - hotel nights not covered (warning, grouped into ranges),
  - flights/hotels/POIs outside the trip dates (warning),
  - planned costs over budget (warning).
- Full JSON export/import, including nested flights, hotels, POIs, and budget
  lines; export all trips or just one.
- Menu-driven interactive mode with no arguments, plus `--demo`.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo

python3 solution.py --db travel.db --add-trip --name "Iceland Ring Road" \
    --destination Iceland --start 2026-06-01 --end 2026-06-08 \
    --notes "Camper van" --currency ISK

python3 solution.py --db travel.db --add-flight --trip 1 --airline IceAir \
    --flight-no IA1 --from BOS --to KEF --depart "2026-06-01 20:00" \
    --arrive "2026-06-02 06:00" --confirmation ABC123 --cost 650.50

python3 solution.py --db travel.db --add-hotel --trip 1 --name "Reykjavik Inn" \
    --city Reykjavik --checkin 2026-06-02 --checkout 2026-06-05 --cost 480

python3 solution.py --db travel.db --add-poi --trip 1 --name "Blue Lagoon" \
    --date 2026-06-02 --start-time 10:00 --end-time 13:00 --category nature --cost 75

python3 solution.py --db travel.db --add-budget --trip 1 --category transport \
    --description Flights --amount 700

python3 solution.py --db travel.db --trips
python3 solution.py --db travel.db --itinerary 1
python3 solution.py --db travel.db --conflicts 1
python3 solution.py --db travel.db --export-json backup.json
python3 solution.py --db travel.db --export-json one-trip.json --trip 1
python3 solution.py --db travel.db --import-json backup.json
```

- `--add-trip` requires `--name`, `--destination`, `--start`, `--end`.
- `--add-flight` requires `--trip`, `--airline`, `--flight-no`, `--from`,
  `--to`, `--depart`, `--arrive`; `--cost` and `--confirmation` are optional.
- `--add-hotel` requires `--trip`, `--name`, `--city`, `--checkin`,
  `--checkout`.
- `--add-poi` requires `--trip`, `--name`, `--date`, `--start-time`,
  `--end-time`; `--category`/`--notes`/`--cost` are optional.
- `--add-budget` requires `--trip`, `--category`, `--amount`.
- `--trips`, `--itinerary ID`, `--conflicts ID` — browse and validate.
- `--export-json FILE` / `--import-json FILE` — backup/share; add `--trip ID`
  to export just one trip.
- `--db` — SQLite file (default `travel.db`).
- `--demo` — build a Kyoto/Osaka sample in a temporary database, print the
  itinerary and conflicts, then JSON round-trip it.

Times are naive local times (`YYYY-MM-DD HH:MM`) and POI times are `HH:MM`;
no timezone conversion is attempted.

## Example Output

```
Kyoto & Osaka Spring — Japan
2026-04-10 to 2026-04-15  ·  6 day(s)  ·  USD

Friday, April 10, 2026
  ✈ Pacific Air PA 118  SFO 09:00 → KIX 13:00  $950.00
  🏨 Check in: Kyoto Ryokan (Kyoto)  conf RYO-4412  $720.00

Saturday, April 11, 2026
  🏨 Staying at Kyoto Ryokan (Kyoto)
  • 09:00-11:00  Fushimi Inari Shrine [sightseeing]
      Walk the torii gate path before the crowds.
  • 10:30-11:30  Tea ceremony [culture]  $60.00
      Reserved at Camellia Tea House.
...
COST SUMMARY
  Flights: 2 · $1,900.00
  Hotels:  2 stay(s), 5 night(s) · $1,260.00
  POIs:    5 · $117.00
  Planned total: $3,277.00
  Budget:  $3,760.00  ·  Remaining $483.00

Conflict check for 'Kyoto & Osaka Spring':
  [WARNING] POIs 'Fushimi Inari Shrine' and 'Tea ceremony' overlap on 2026-04-11

0 error(s), 1 warning(s).
Exported 1 trip and 13 items to JSON (3,427 bytes)
Imported 1 trip and 13 items into a fresh database
Round-trip totals match: True (planned $3,277.00, 5 hotel nights)
```

## Implementation Notes

All costs are integer cents; `--cost` and `--amount` accept dollars with
optional `$` and thousands separators. Dates and times are ISO strings in
SQLite, so ordering and range comparisons are straightforward. Foreign keys
cascade child rows when a trip is deleted (the CLI does not expose trip
deletion, but the schema is ready for it).

The itinerary walks each date of the trip and clips items: flights appear on
their departure date with a `(+1)` marker for next-day arrivals, and also as an
arrival line on the following day; hotels appear from check-in through checkout
(labelled check-in, staying, or check-out); POIs appear on their date sorted by
start time. Daily costs are shown on the item line, while the trip summary sums
all costs once.

Conflict checks are interval comparisons in Python: flights by datetime,
hotels by date ranges, POIs by same-day time ranges. Missing hotel nights are
computed over `trip_start .. trip_end - 1` and compressed into consecutive
ranges. An overnight flight still triggers a "no hotel" warning if the first
night is uncovered — deliberate, because the traveller may need a room on
arrival day or a plan for the overnight leg.

JSON import validates dates, times, and ordering before inserting, but it
appends trips: importing the same file twice creates duplicates. The export
format is versioned (`"format": "travel-planner", "version": 1`) and stores
`cost_cents` / `amount_cents` as integers.
