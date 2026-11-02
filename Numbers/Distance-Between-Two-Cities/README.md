# Distance Between Two Cities

**Category:** Numbers · **Project:** `Distance-Between-Two-Cities`

## Problem

> Calculates the distance between two cities and allows the user to specify a unit of distance. This program may require finding coordinates for the cities like latitude and longitude.

## Features

- Embedded gazetteer of **65 world cities** on six continents, so the program is fully offline.
- Case-insensitive lookup with accent folding and aliases (`NYC`, `SF`, `Bombay`, `Kiev`, `São Paulo`).
- Great-circle distance via the haversine formula, plus the initial compass bearing.
- Units: kilometres, miles, nautical miles, metres and feet.
- `--geocode` fallback queries OpenStreetMap Nominatim only when a city is missing; network
  failures produce a warning and fall back to the offline table instead of crashing.
- `--list-cities` prints the gazetteer; unknown names get `difflib` spelling suggestions.
- `--demo` exercises four pairs and every unit conversion without network access.

## Requirements

Python 3.10 or newer. Standard library only — no packages to install.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --from London --to Tokyo
python3 solution.py --from "New York" --to "San Francisco" --unit mi
python3 solution.py --from "Sao Paulo" --to Nairobi --geocode
python3 solution.py --list-cities
```

- `--from CITY` / `--to CITY` — the two endpoints; prompted interactively if omitted.
- `--unit {km,mi,nmi,m,ft}` — output unit (default `km`).
- `--geocode` — allow a Nominatim lookup for names not in the offline table.
- `--list-cities` — show all embedded coordinates and countries.
- `--demo` — run the offline demonstration.

## Example Output

```text
Distance Between Two Cities demo
Offline gazetteer: 65 cities
----------------------------------------------------------
London (United Kingdom) -> Paris (France)
  distance: 343.56 km
  initial bearing: 148.1 deg

New York (United States) -> Los Angeles (United States)
  distance: 2,445.56 mi
            (3,935.75 km great-circle)
  initial bearing: 273.7 deg

Tokyo (Japan) -> Sydney (Australia)
  distance: 7,825.83 km
  initial bearing: 169.8 deg

Cape Town (South Africa) -> Cairo (Egypt)
  distance: 3,908.89 nmi
            (7,239.26 km great-circle)
  initial bearing: 12.2 deg

Unit conversions for London -> Paris:
  343.56 km
  213.48 mi
  185.51 nmi
  343,557 m
  1,127,154 ft
```

## Implementation Notes

Distances use the haversine formula with a mean Earth radius of 6371.0088 km:

`d = 2R · asin(√(sin²(Δφ/2) + cos φ₁ · cos φ₂ · sin²(Δλ/2)))`

This gives great-circle (as-the-crow-flies) distances, not road or flight-path
distances. Coordinates are approximate city-centre points, so results are
typically within a few kilometres of authoritative figures. Nominatim requests
send a descriptive User-Agent and a 5-second timeout; the public service has
usage limits, so bulk use should use a local dataset instead.
