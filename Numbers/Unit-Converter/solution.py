#!/usr/bin/env python3
"""Convert values between units of temperature, currency, volume and more.

Categories: length, mass, volume, area, speed, time, data, temperature and
currency.  Conversion logic lives in :mod:`converter`; unit tables live in
:mod:`unit_data`.  Currency uses a static offline rate table that can be
overridden with ``--rates FILE``.  No network access is performed.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation

from converter import (
    CATEGORIES,
    convert,
    format_number,
    load_rates,
    resolve_unit,
    temperature_convert,
)
from unit_data import DEFAULT_RATES, TEMPERATURE_UNITS, UNITS, UNIT_NAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert between units of length, mass, volume, area, speed, "
        "time, data, temperature and currency.",
        epilog=(
            "Examples: solution.py --category length --from km --to mi --value 100 | "
            "solution.py --list"
        ),
    )
    parser.add_argument("--category", choices=CATEGORIES, help="unit category")
    parser.add_argument("--from", dest="from_unit", metavar="UNIT", help="source unit")
    parser.add_argument("--to", dest="to_unit", metavar="UNIT", help="target unit")
    parser.add_argument("--value", help="value to convert")
    parser.add_argument(
        "--precision",
        type=int,
        default=6,
        metavar="N",
        help="decimal places in the result (default: 6)",
    )
    parser.add_argument(
        "--list", action="store_true", help="list categories or units in a category"
    )
    parser.add_argument(
        "--rates", metavar="JSON", help="currency rates file (code -> units per USD)"
    )
    parser.add_argument("--demo", action="store_true", help="run scripted conversions")
    return parser


def print_categories() -> None:
    """List every category with its unit symbols."""
    for category in CATEGORIES:
        if category == "temperature":
            symbols = ", ".join(TEMPERATURE_UNITS)
        elif category == "currency":
            symbols = ", ".join(DEFAULT_RATES)
        else:
            symbols = ", ".join(UNITS[category])
        print(f"{category:<12} {symbols}")


def print_units(category: str) -> None:
    """Show full unit names for one category."""
    if category == "temperature":
        for symbol, name in TEMPERATURE_UNITS.items():
            print(f"  {symbol:<6} {name}")
    elif category == "currency":
        for symbol, rate in DEFAULT_RATES.items():
            print(f"  {symbol:<6} 1 USD = {rate} {symbol} (static offline rate)")
    else:
        for symbol, name in UNIT_NAMES[category].items():
            print(f"  {symbol:<6} {name}")


def run_demo() -> int:
    """Print a deterministic table of representative conversions."""
    print("Unit converter demo")
    print("=" * 19)
    print(f"{'Category':<12} {'Conversion':<30} {'Result':>14}")
    samples = [
        ("length", "km", "mi", "100"),
        ("temperature", "F", "C", "72"),
        ("area", "acre", "m2", "1"),
        ("volume", "l", "gal", "2.5"),
        ("mass", "lb", "kg", "180"),
        ("speed", "mph", "km/h", "60"),
        ("data", "GiB", "MiB", "1"),
        ("time", "day", "h", "2"),
        ("currency", "USD", "EUR", "100"),
    ]
    for category, source, target, raw in samples:
        value = Decimal(raw)
        result = convert(category, source, target, value)
        label = f"{raw} {source} -> {target}"
        print(f"{category:<12} {label:<30} {format_number(result, 6):>14}")

    print("\nTemperature checks:")
    print(
        f"  -40 F -> C = "
        f"{format_number(temperature_convert('F', 'C', Decimal('-40')), 4)}"
    )
    print(
        f"  0 K -> C  = "
        f"{format_number(temperature_convert('K', 'C', Decimal('0')), 4)}"
    )

    print("\nCurrency rates are static/offline; use --rates JSON to override.")
    return 0


def interactive(rates: dict[str, Decimal]) -> int:
    """Ask for category, units and a value, then convert once."""
    print("Categories: " + ", ".join(CATEGORIES))
    try:
        category = input("Category: ").strip().lower()
        if category not in CATEGORIES:
            print(f"Error: unknown category: {category!r}", file=sys.stderr)
            return 2
        print_units(category)
        from_unit = resolve_unit(category, input("From unit: "), rates)
        to_unit = resolve_unit(category, input("To unit: "), rates)
        value = Decimal(input("Value: ").strip().replace(",", ""))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (ValueError, InvalidOperation) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = convert(category, from_unit, to_unit, value, rates)
    print(
        f"{format_number(value, 10)} {from_unit} = "
        f"{format_number(result, 6)} {to_unit}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.precision < 0 or args.precision > 15:
        parser.error("--precision must be between 0 and 15")

    if args.demo:
        return run_demo()

    if args.list:
        if args.category:
            print_units(args.category)
        else:
            print_categories()
        return 0

    try:
        rates = load_rates(args.rates) if args.rates else DEFAULT_RATES
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.category is None:
        return interactive(rates)

    try:
        if not (args.from_unit and args.to_unit and args.value is not None):
            parser.error("--category requires --from, --to and --value")
        value = Decimal(args.value.strip().replace(",", ""))
        if not value.is_finite():
            raise ValueError("value must be finite")
        source = resolve_unit(args.category, args.from_unit, rates)
        target = resolve_unit(args.category, args.to_unit, rates)
        result = convert(args.category, source, target, value, rates)
    except (ValueError, InvalidOperation) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(
        f"{format_number(value, 10)} {source} = "
        f"{format_number(result, args.precision)} {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
