#!/usr/bin/env python3
"""Convert between decimal and binary, including fractional values.

Examples:
    42          <-> 101010
    10.625      <-> 1010.101
    -0.5        <-> -0.1

Fractional decimal values that are not sums of powers of two are truncated
after ``--places`` bits; the program says so when that happens.
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext

BINARY_RE = re.compile(r"^[+-]?[01]+(?:\.[01]+)?$")


def decimal_to_binary(value: Decimal, places: int = 16) -> tuple[str, bool]:
    """Convert a Decimal to binary.

    Returns ``(text, exact)``; ``exact`` is False when the fraction had to be
    truncated at ``places`` bits.
    """
    if places < 0:
        raise ValueError("places must be non-negative")

    sign = "-" if value < 0 else ""
    value = abs(value)
    integer_part = int(value.to_integral_value(rounding=ROUND_FLOOR))
    fraction = value - integer_part

    bits: list[str] = []
    while fraction and len(bits) < places:
        fraction *= 2
        bit = int(fraction)
        bits.append(str(bit))
        fraction -= bit

    text = f"{integer_part:b}"
    if bits:
        text += "." + "".join(bits)
    return sign + text, fraction == 0


def binary_to_decimal(text: str) -> Decimal:
    """Convert a binary string (optional sign and point) to Decimal."""
    cleaned = text.strip().replace("_", "").replace(" ", "")
    if cleaned.lower().startswith(("0b", "+0b", "-0b")):
        sign = "-" if cleaned.startswith("-") else ""
        cleaned = sign + cleaned[3:] if sign else cleaned[2:]
    if not BINARY_RE.match(cleaned):
        raise ValueError(f"not a valid binary number: {text!r}")

    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("+-")
    integer_text, _, fraction_text = cleaned.partition(".")

    with localcontext() as ctx:
        ctx.prec = max(50, len(fraction_text) + 20)
        result = Decimal(int(integer_text, 2))
        for index, bit in enumerate(fraction_text, start=1):
            if bit == "1":
                result += Decimal(1) / (Decimal(2) ** index)
    return -result if negative else result


def group_bits(text: str, size: int = 4) -> str:
    """Group binary digits in blocks, separately for integer and fraction."""
    sign = ""
    if text.startswith(("+", "-")):
        sign, text = text[0], text[1:]
    integer, dot, fraction = text.partition(".")

    chunks = []
    for end in range(len(integer), 0, -size):
        chunks.append(integer[max(0, end - size) : end])
    grouped_int = " ".join(reversed(chunks)) if chunks else "0"

    grouped_fraction = " ".join(
        fraction[start : start + size] for start in range(0, len(fraction), size)
    )
    result = sign + grouped_int
    if dot and grouped_fraction:
        result += "." + grouped_fraction
    return result


def parse_decimal(raw: str) -> Decimal:
    """Parse a decimal number with underscores or thousands commas."""
    cleaned = raw.strip().replace("_", "").replace(",", "")
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"not a decimal number: {raw!r}") from exc
    if not value.is_finite():
        raise ValueError("value must be finite")
    return value


def format_decimal(value: Decimal) -> str:
    """Format a Decimal without exponent notation or trailing zeros."""
    text = format(value.normalize(), "f")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert decimal numbers to binary and back.",
        epilog=(
            "Examples: solution.py --to-binary 10.625 | "
            "solution.py --to-decimal 1010.101"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--to-binary", metavar="DECIMAL", help="decimal value to convert")
    group.add_argument("--to-decimal", metavar="BINARY", help="binary value to convert")
    parser.add_argument(
        "--places",
        type=int,
        default=16,
        metavar="N",
        help="maximum fraction bits when converting to binary (default: 16)",
    )
    parser.add_argument(
        "--group", action="store_true", help="group binary digits in blocks of four"
    )
    parser.add_argument("--demo", action="store_true", help="run scripted conversions")
    return parser


def run_demo() -> int:
    """Show integers, fractions, signs, prefixes and grouping."""
    print("Decimal -> binary")
    for raw in ("42", "10.625", "-0.5", "0.1", "255"):
        value = Decimal(raw)
        text, exact = decimal_to_binary(value, 20)
        suffix = "" if exact else "  (truncated at 20 fraction bits)"
        print(f"  {raw:>7} -> {text}{suffix}")

    print("\nBinary -> decimal")
    for raw in ("101010", "1010.101", "-0.1", "0b11111111"):
        print(f"  {raw:>12} -> {format_decimal(binary_to_decimal(raw))}")

    print("\nGrouped presentation")
    text, _ = decimal_to_binary(Decimal("3054"), 8)
    print(f"  3054 -> {group_bits(text)}")

    print("\nRound-trip check")
    original = Decimal("123.375")
    encoded, _ = decimal_to_binary(original, 20)
    decoded = binary_to_decimal(encoded)
    print(f"  {original} -> {encoded} -> {format_decimal(decoded)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.places < 0 or args.places > 200:
        parser.error("--places must be between 0 and 200")

    if args.demo:
        return run_demo()

    try:
        if args.to_binary is not None:
            text, exact = decimal_to_binary(parse_decimal(args.to_binary), args.places)
            print(group_bits(text) if args.group else text)
            if not exact:
                print(
                    f"Note: fraction truncated at {args.places} bits.",
                    file=sys.stderr,
                )
            return 0

        if args.to_decimal is not None:
            value = binary_to_decimal(args.to_decimal)
            print(format_decimal(value))
            return 0

        direction = input("Convert [1] decimal->binary or [2] binary->decimal? ").strip()
        if direction == "1":
            raw = input("Decimal value: ")
            text, exact = decimal_to_binary(parse_decimal(raw), args.places)
            print(group_bits(text) if args.group else text)
            if not exact:
                print(f"Note: fraction truncated at {args.places} bits.", file=sys.stderr)
        elif direction == "2":
            print(format_decimal(binary_to_decimal(input("Binary value: "))))
        else:
            print("Error: choose 1 or 2.", file=sys.stderr)
            return 2
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
