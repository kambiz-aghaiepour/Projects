#!/usr/bin/env python3
"""Estimate the cost of tiling a rectangular floor.

Two pricing modes are supported:

* area pricing -- a price per square foot/metre, optionally with waste;
* tile pricing -- tile dimensions and a price per tile, with whole tiles
  rounded up per direction.

All money arithmetic uses :class:`decimal.Decimal`.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

CENT = Decimal("0.01")


@dataclass(frozen=True)
class AreaQuote:
    """Quote produced by per-area pricing."""

    area: Decimal
    billable_area: Decimal
    total: Decimal


@dataclass(frozen=True)
class TileQuote:
    """Quote produced by per-tile pricing."""

    area: Decimal
    tiles_x: int
    tiles_y: int
    base_tiles: int
    tiles: int
    total: Decimal


def number(value: Decimal) -> str:
    """Render a Decimal without insignificant trailing zeros."""
    return format(value.normalize(), "f")


def money(value: Decimal) -> str:
    """Format a Decimal as a plain money amount with two decimals."""
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def positive(raw: str, label: str) -> Decimal:
    """Parse a strictly positive Decimal."""
    try:
        value = Decimal(raw.strip().replace(",", ""))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"{label} must be a number: {raw!r}") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


def non_negative(raw: str, label: str) -> Decimal:
    """Parse a non-negative Decimal."""
    try:
        value = Decimal(raw.strip().replace(",", ""))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"{label} must be a number: {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value


def calculate_area_cost(
    width: Decimal, height: Decimal, unit_cost: Decimal, waste_percent: Decimal
) -> AreaQuote:
    """Cost from floor area and a price per square unit."""
    area = width * height
    waste_factor = Decimal(1) + waste_percent / Decimal(100)
    billable_area = area * waste_factor
    total = (billable_area * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
    return AreaQuote(area=area, billable_area=billable_area, total=total)


def calculate_tile_cost(
    width: Decimal,
    height: Decimal,
    tile_width: Decimal,
    tile_height: Decimal,
    tile_cost: Decimal,
    waste_percent: Decimal,
) -> TileQuote:
    """Cost from tile dimensions; tiles are rounded up per direction."""
    tiles_x = int((width / tile_width).to_integral_value(rounding=ROUND_CEILING))
    tiles_y = int((height / tile_height).to_integral_value(rounding=ROUND_CEILING))
    base_tiles = tiles_x * tiles_y
    waste_factor = Decimal(1) + waste_percent / Decimal(100)
    tiles = int(
        (Decimal(base_tiles) * waste_factor).to_integral_value(rounding=ROUND_CEILING)
    )
    total = (Decimal(tiles) * tile_cost).quantize(CENT, rounding=ROUND_HALF_UP)
    return TileQuote(
        area=width * height,
        tiles_x=tiles_x,
        tiles_y=tiles_y,
        base_tiles=base_tiles,
        tiles=tiles,
        total=total,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate how much tile is needed and what it costs.",
        epilog="Run with no arguments to be prompted for dimensions and prices.",
    )
    parser.add_argument("--width", help="floor width")
    parser.add_argument("--height", help="floor height")
    parser.add_argument(
        "--unit-cost",
        help="price per square unit (omit when using --tile-cost)",
    )
    parser.add_argument("--tile-width", help="width of one tile (tile mode)")
    parser.add_argument("--tile-height", help="height of one tile (tile mode)")
    parser.add_argument("--tile-cost", help="price of one tile (tile mode)")
    parser.add_argument(
        "--waste",
        default="0",
        metavar="PERCENT",
        help="extra material percentage (default: 0)",
    )
    parser.add_argument(
        "--unit", default="ft", help="length unit label for display (default: ft)"
    )
    parser.add_argument("--demo", action="store_true", help="run scripted examples")
    return parser


def ask(prompt: str) -> str:
    """Prompt for a value, translating EOF into a clean cancellation."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt) as exc:
        raise ValueError("cancelled") from exc


def run_demo() -> int:
    """Print deterministic area and tile pricing examples."""
    print("Example 1: 12 x 10 ft floor at $3.50 per sq ft, 10% waste")
    area_quote = calculate_area_cost(
        Decimal("12"), Decimal("10"), Decimal("3.50"), Decimal("10")
    )
    print(f"  Floor area:       {number(area_quote.area)} sq ft")
    print(f"  With 10% waste:   {number(area_quote.billable_area)} sq ft")
    print(f"  Total cost:       ${money(area_quote.total)}")

    print("\nExample 2: 5 x 4 m floor with 30 x 30 cm tiles at $2.25 each")
    tile_quote = calculate_tile_cost(
        Decimal("5"),
        Decimal("4"),
        Decimal("0.30"),
        Decimal("0.30"),
        Decimal("2.25"),
        Decimal("10"),
    )
    print(
        f"  Tile grid:        {tile_quote.tiles_x} x {tile_quote.tiles_y} "
        f"= {tile_quote.base_tiles} tiles"
    )
    print(f"  With 10% waste:   {tile_quote.tiles} tiles")
    print(f"  Total cost:       ${money(tile_quote.total)}")

    print("\nExample 3: 3 x 2.5 m floor at $48.00 per sq m, no waste")
    last = calculate_area_cost(
        Decimal("3"), Decimal("2.5"), Decimal("48.00"), Decimal("0")
    )
    print(f"  Total cost:       ${money(last.total)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    try:
        width = positive(
            args.width if args.width is not None else ask("Floor width: "), "width"
        )
        height = positive(
            args.height if args.height is not None else ask("Floor height: "), "height"
        )
        waste = non_negative(args.waste, "waste")

        tile_mode = any(
            value is not None
            for value in (args.tile_width, args.tile_height, args.tile_cost)
        )
        if tile_mode and args.unit_cost is not None:
            parser.error("use either --unit-cost or tile options, not both")

        if tile_mode:
            if not all((args.tile_width, args.tile_height, args.tile_cost)):
                parser.error("tile mode needs --tile-width, --tile-height and --tile-cost")
            quote = calculate_tile_cost(
                width,
                height,
                positive(args.tile_width or "", "tile width"),
                positive(args.tile_height or "", "tile height"),
                positive(args.tile_cost or "", "tile cost"),
                waste,
            )
            print(f"Floor area: {number(quote.area)} sq {args.unit}")
            print(
                f"Tiles needed: {quote.tiles} "
                f"({quote.tiles_x} x {quote.tiles_y} grid, {waste}% waste)"
            )
            print(f"Total cost: ${money(quote.total)}")
        else:
            raw_cost = (
                args.unit_cost
                if args.unit_cost is not None
                else ask(f"Cost per sq {args.unit}: ")
            )
            area_quote = calculate_area_cost(
                width, height, positive(raw_cost, "unit cost"), waste
            )
            print(f"Floor area: {number(area_quote.area)} sq {args.unit}")
            print(f"Area with waste: {number(area_quote.billable_area)} sq {args.unit}")
            print(f"Total cost: ${money(area_quote.total)}")
    except (ValueError, ArithmeticError) as exc:
        message = str(exc)
        print(
            "Cancelled." if message == "cancelled" else f"Error: {message}",
            file=sys.stderr,
        )
        return 0 if message == "cancelled" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
