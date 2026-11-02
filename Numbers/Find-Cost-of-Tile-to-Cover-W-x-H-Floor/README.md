# Find Cost of Tile to Cover W x H Floor

**Category:** Numbers · **Project:** `Find-Cost-of-Tile-to-Cover-W-x-H-Floor`

## Problem

Calculate the total cost of tile it would take to cover a floor plan of width and height, using a cost entered by the user.

## Features

- Area pricing: price per square foot/metre, with an optional waste percentage.
- Tile pricing: tile width/height and price per tile, rounding whole tiles up
  in each direction.
- Exact `Decimal` money arithmetic and half-up rounding to cents.
- Worked demo with three scenarios, including a metric tile layout.
- Interactive prompts when dimensions or prices are omitted.
- Custom unit label for display (`--unit m`, `--unit ft`, …).

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --width 12 --height 10 --unit-cost 3.50 --waste 10
python3 solution.py --width 5 --height 4 --tile-width 0.30 --tile-height 0.30 --tile-cost 2.25 --waste 10 --unit m
```

- `--width`, `--height` — floor dimensions.
- `--unit-cost` — price per square unit of floor area.
- `--tile-width`, `--tile-height`, `--tile-cost` — per-tile pricing instead.
- `--waste PERCENT` — extra material allowance (default 0).
- `--unit LABEL` — length unit shown in output (default `ft`).
- `--demo` — run the scripted examples.

## Example Output

```text
Example 1: 12 x 10 ft floor at $3.50 per sq ft, 10% waste
  Floor area:       120 sq ft
  With 10% waste:   132 sq ft
  Total cost:       $462.00

Example 2: 5 x 4 m floor with 30 x 30 cm tiles at $2.25 each
  Tile grid:        17 x 14 = 238 tiles
  With 10% waste:   262 tiles
  Total cost:       $589.50

Example 3: 3 x 2.5 m floor at $48.00 per sq m, no waste
  Total cost:       $360.00
```

## Implementation Notes

Area mode multiplies width × height by `1 + waste/100` and then by the unit
price. Tile mode rounds `width / tile_width` and `height / tile_height` up
independently to whole tiles (a straight lay, no pattern offsets), multiplies
the grid, applies waste, rounds up again, and multiplies by the tile price.
All Decimal results are quantized to cents with `ROUND_HALF_UP`.

The program assumes a rectangular floor and identical, non-overlapping tiles.
It does not model grout lines, cuts, plank layouts, or sales tax.
