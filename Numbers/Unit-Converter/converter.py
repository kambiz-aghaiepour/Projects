"""Conversion engine for the unit converter.

Handles unit-name resolution, temperature formulas, currency rates and
numeric formatting.  Unit tables live in :mod:`unit_data`.
"""

from __future__ import annotations

import difflib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path

from unit_data import ALIASES, DEFAULT_RATES, TEMPERATURE_UNITS, UNITS

CATEGORIES = tuple(UNITS) + ("temperature", "currency")


def resolve_unit(
    category: str, raw: str, currency_rates: dict[str, Decimal] | None = None
) -> str:
    """Resolve a unit symbol or alias to its canonical symbol."""
    text = raw.strip()
    if category == "temperature":
        candidates = TEMPERATURE_UNITS
        lowered = text.lower()
        for symbol in candidates:
            if lowered == symbol.lower():
                return symbol
        alias = ALIASES[category].get(lowered)
        if alias:
            return alias
        known = list(candidates)
    elif category == "currency":
        candidates = currency_rates or DEFAULT_RATES
        lowered = text.upper()
        if lowered in candidates:
            return lowered
        alias = ALIASES[category].get(text.lower())
        if alias:
            return alias
        known = list(candidates)
    else:
        candidates = UNITS[category]
        if text in candidates:
            return text
        lowered = text.lower()
        for symbol in candidates:
            if symbol.lower() == lowered:
                return symbol
        alias = ALIASES[category].get(lowered)
        if alias:
            return alias
        known = list(candidates)

    suggestions = difflib.get_close_matches(text, known, n=3)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise ValueError(f"unknown {category} unit: {raw!r}.{hint}")


def temperature_convert(from_unit: str, to_unit: str, value: Decimal) -> Decimal:
    """Convert temperature through Celsius as the pivot scale."""
    if from_unit == "C":
        celsius = value
    elif from_unit == "F":
        celsius = (value - Decimal(32)) * Decimal(5) / Decimal(9)
    elif from_unit == "K":
        celsius = value - Decimal("273.15")
    else:  # Rankine
        celsius = value * Decimal(5) / Decimal(9) - Decimal("273.15")

    if celsius < Decimal("-273.15"):
        raise ValueError("temperature is below absolute zero")

    if to_unit == "C":
        return celsius
    if to_unit == "F":
        return celsius * Decimal(9) / Decimal(5) + Decimal(32)
    if to_unit == "K":
        return celsius + Decimal("273.15")
    return (celsius + Decimal("273.15")) * Decimal(9) / Decimal(5)


def load_rates(path: str) -> dict[str, Decimal]:
    """Load a JSON currency table mapping code to units per USD."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read rates file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in rates file: {exc}") from exc
    if not isinstance(raw, dict) or "USD" not in raw:
        raise ValueError("rates file must be an object with a USD entry")
    rates: dict[str, Decimal] = {}
    for code, rate in raw.items():
        try:
            value = Decimal(str(rate))
        except InvalidOperation as exc:
            raise ValueError(f"invalid rate for {code}: {rate!r}") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError(f"rate for {code} must be positive")
        rates[str(code).upper()] = value
    return rates


def convert(
    category: str,
    from_unit: str,
    to_unit: str,
    value: Decimal,
    rates: dict[str, Decimal] | None = None,
) -> Decimal:
    """Convert value between two units of the same category."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category!r}")
    if category == "temperature":
        return temperature_convert(from_unit, to_unit, value)
    if category == "currency":
        table = rates or DEFAULT_RATES
        if from_unit not in table or to_unit not in table:
            raise ValueError("currency code missing from the rate table")
        return value / table[from_unit] * table[to_unit]
    factors = UNITS[category]
    return value * factors[from_unit] / factors[to_unit]


def format_number(value: Decimal, precision: int) -> str:
    """Round to ``precision`` decimal places and trim trailing zeros."""
    if value == 0:
        return "0"
    # Leave room for large integer parts so quantize cannot overflow the
    # default 28-digit context for extreme (but valid) conversions.
    context_digits = max(28, value.adjusted() + precision + 3)
    with localcontext() as ctx:
        ctx.prec = context_digits
        quantum = Decimal(1).scaleb(-precision)
        rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
        text = format(rounded, "f")
    if rounded == 0 and value != 0:
        return format(value.normalize(), "e").lower()
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
