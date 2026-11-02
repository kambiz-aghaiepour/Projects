# Fetch Current Weather

**Category:** Web · **Project:** Fetch-Current-Weather

## Problem

Get the current weather for a given zip/postal code. Optional: try locating the
user automatically.

## Features

- City-name lookup through the Open-Meteo geocoding API.
- US ZIP code support (automatic for five-digit input) and international postal
  codes via Zippopotam.us with `--postal --country XX`.
- Current conditions: temperature, apparent temperature, humidity, wind speed
  and compass direction, precipitation, daylight flag, and a WMO condition
  description with symbol.
- Multi-day forecast (1–16 days) with daily low/high temperatures and maximum
  precipitation probability.
- Metric or imperial units, converted server-side by Open-Meteo.
- `--auto-locate` optionally estimates the user's position from their public IP
  address (no API key).
- `--json` machine-readable output.
- `--demo` renders bundled Open-Meteo sample JSON for Boston — fully offline.

## Requirements

Python 3.10+ only; standard library. Live lookups need internet access but no
API key. The three services used (Open-Meteo geocoding, Open-Meteo forecast,
Zippopotam.us) are free and keyless; IP geolocation uses ipapi.co.

## Usage

```bash
python3 solution.py --demo
python3 solution.py "Boston, MA"
python3 solution.py 90210
python3 solution.py 10115 --postal --country de
python3 solution.py "Berlin" --country de --days 7 --units metric
python3 solution.py --auto-locate --units imperial
python3 solution.py "Tokyo" --json
```

| Option | Meaning |
| --- | --- |
| `location` | City name, or postal code with `--postal` / a five-digit US ZIP. |
| `--postal` | Interpret the location as a postal code. |
| `--country CC` | ISO country code; defaults to `us` for postal lookups and optionally filters city searches. |
| `--units {metric,imperial}` | °C/km/h/mm or °F/mph/inch (default metric). |
| `--days N` | Forecast length, 1–16 (default 5). |
| `--auto-locate` | Approximate the location from the public IP instead of an argument. |
| `--timeout SECONDS` | HTTP timeout (default 10). |
| `--json` | Print JSON rather than the formatted report. |
| `--demo` | Run the offline demonstration. |

With no location the program prompts interactively. `--auto-locate` is
approximate (often city-level) and depends on a third-party IP database.

## Example Output

```
Fetch Current Weather demo (offline: bundled Open-Meteo sample JSON)

Sample data: sample_data/geocode_boston.json, forecast_boston.json

Weather for Boston, Massachusetts, United States
Location: 42.3584, -71.0598 · timezone America/New_York (EST)

Current conditions — 2026-11-02 14:00 local
  ☁  Overcast (WMO 3)
  Temperature:   12.4 °C (feels like 11.0 °C)
  Humidity:      55%
  Wind:          14.2 km/h from SSW (210°)
  Precipitation: 0.0 mm
  Daylight:      yes

5-day forecast:
  Day          Condition                          Low … High   Rain
  ------------------------------------------------------------------
  Mon 02 Nov   Overcast                        7.1 … 14.2 °C    20%
  Tue 03 Nov   Slight rain                     6.4 … 12.8 °C    80%
  Wed 04 Nov   Partly cloudy                   4.2 … 10.1 °C    10%
  Thu 05 Nov   Clear sky                        2.8 … 9.4 °C     0%
  Fri 06 Nov   Fog                             3.9 … 11.0 °C    15%

Unit conversion check (for --units imperial): 12.4 °C = 54.3 °F; 14.2 km/h = 8.8 mph.

Demo complete: 5-day sample forecast rendered, all checks passed (no network used).
```

## Implementation Notes

`geocode_city` calls
`https://geocoding-api.open-meteo.com/v1/search?name=…&count=1`, taking the first
result's latitude, longitude and timezone. Postal codes go to
`https://api.zippopotam.us/{country}/{postal}`, which returns the place name,
state and coordinates. `fetch_forecast` then requests current and daily fields
from `https://api.open-meteo.com/v1/forecast` with `timezone=auto`, so all
timestamps are local to the chosen place; imperial requests set
`temperature_unit=fahrenheit`, `wind_speed_unit=mph` and
`precipitation_unit=inch`, and the unit labels come back in the payload.

The renderer treats missing daily arrays defensively, mapping indices to values
only when present. WMO codes are translated through a complete 28-entry table,
and wind bearings are rounded to a 16-point compass. The bundled sample files in
`sample_data/` are literal Open-Meteo-shaped payloads, so `--demo` exercises the
same parsing and rendering code as a live request.

Limitations: city geocoding can return a same-named place in another region
(use `--country` to narrow it); Zippopotam.us does not cover every country;
`--auto-locate` is approximate and rate-limited; forecasts are model output, not
observations. The demo data is fixed at 2026-11-02 for deterministic output.
