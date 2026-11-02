# Unit Converter (temp, currency, volume, mass and more)

**Category:** Numbers · **Project:** `Unit-Converter`

## Problem

Converts various units between one another. The user enters the type of unit being entered, the type of unit they want to convert to and then the value. The program will then make the conversion.

## Features

- Nine categories: length, mass, volume, area, speed, time, data, temperature,
  currency.
- Friendly unit names and symbols (`kilometers`, `km`, `miles`, `mi`, …).
- Temperature conversion through Celsius with an absolute-zero check.
- Static offline currency table, overridable with `--rates FILE` (JSON mapping
  currency code to units per USD).
- `--list` shows every category, or every unit in one category.
- Configurable rounding precision; interactive menu when no arguments given.

## Requirements

Python 3.10+ and the standard library only. No network access is required.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --list
python3 solution.py --list --category volume
python3 solution.py --category length --from km --to mi --value 100
python3 solution.py --category temperature --from F --to C --value 72
python3 solution.py --category currency --from USD --to EUR --value 100
python3 solution.py --category currency --from USD --to EUR --value 100 --rates my_rates.json
```

- `--category` — one of the nine categories.
- `--from`, `--to` — unit symbols or names; aliases are accepted.
- `--value` — numeric value to convert.
- `--precision N` — decimal places in the result (0–15, default 6).
- `--list` — list categories, or units when combined with `--category`.
- `--rates JSON` — replace the built-in currency table.
- `--demo` — print representative conversions and exit.

## Example Output

```text
Unit converter demo
===================
Category     Conversion                             Result
length       100 km -> mi                        62.137119
temperature  72 F -> C                           22.222222
area         1 acre -> m2                      4046.856422
volume       2.5 l -> gal                          0.66043
mass         180 lb -> kg                        81.646627
speed        60 mph -> km/h                       96.56064
data         1 GiB -> MiB                             1024
time         2 day -> h                                 48
currency     100 USD -> EUR                             92

Temperature checks:
  -40 F -> C = -40
  0 K -> C  = -273.15

Currency rates are static/offline; use --rates JSON to override.
```

## Implementation Notes

Unit tables live in `unit_data.py` and conversion logic in `converter.py`.
Each linear category stores factors relative to a base unit, so conversion is
`value × factor_from / factor_to`. Temperature is not linear across scales and
uses explicit Celsius-pivot formulas, rejecting results below absolute zero.
Currency uses units-per-USD rates and the same ratio approach.

The currency table is illustrative and static, not live market data; pass
`--rates` for your own snapshot. Volume units are US liquid measures, mass
tonnes are metric, and a year is the Julian year (365.25 days). The display
label preserves the canonical symbol rather than the alias supplied by the
user.
