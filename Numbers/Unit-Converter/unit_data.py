"""Static unit tables for the unit converter.

Every linear unit stores its size relative to the category's base unit:
metre (length), kilogram (mass), litre (volume), square metre (area),
metre per second (speed), second (time), byte (data).  Temperature uses
formulas in ``solution.py``; currency rates are illustrative offline values,
not live market data, and can be replaced with ``--rates``.
"""

from __future__ import annotations

from decimal import Decimal

UNITS: dict[str, dict[str, Decimal]] = {
    "length": {
        "m": Decimal("1"),
        "km": Decimal("1000"),
        "cm": Decimal("0.01"),
        "mm": Decimal("0.001"),
        "mi": Decimal("1609.344"),
        "yd": Decimal("0.9144"),
        "ft": Decimal("0.3048"),
        "in": Decimal("0.0254"),
        "nmi": Decimal("1852"),
    },
    "mass": {
        "kg": Decimal("1"),
        "g": Decimal("0.001"),
        "mg": Decimal("0.000001"),
        "t": Decimal("1000"),
        "lb": Decimal("0.45359237"),
        "oz": Decimal("0.028349523125"),
        "st": Decimal("6.35029318"),
    },
    "volume": {
        "l": Decimal("1"),
        "ml": Decimal("0.001"),
        "m3": Decimal("1000"),
        "gal": Decimal("3.785411784"),
        "qt": Decimal("0.946352946"),
        "pt": Decimal("0.473176473"),
        "cup": Decimal("0.2365882365"),
        "floz": Decimal("0.0295735295625"),
        "tbsp": Decimal("0.01478676478125"),
        "tsp": Decimal("0.00492892159375"),
    },
    "area": {
        "m2": Decimal("1"),
        "km2": Decimal("1000000"),
        "cm2": Decimal("0.0001"),
        "ha": Decimal("10000"),
        "acre": Decimal("4046.8564224"),
        "ft2": Decimal("0.09290304"),
        "in2": Decimal("0.00064516"),
        "mi2": Decimal("2589988.110336"),
    },
    "speed": {
        "m/s": Decimal("1"),
        "km/h": Decimal("0.2777777777777777777777777778"),
        "mph": Decimal("0.44704"),
        "knot": Decimal("0.5144444444444444444444444444"),
        "ft/s": Decimal("0.3048"),
    },
    "time": {
        "s": Decimal("1"),
        "min": Decimal("60"),
        "h": Decimal("3600"),
        "day": Decimal("86400"),
        "week": Decimal("604800"),
        "year": Decimal("31557600"),
    },
    "data": {
        "B": Decimal("1"),
        "kB": Decimal("1000"),
        "MB": Decimal("1000000"),
        "GB": Decimal("1000000000"),
        "TB": Decimal("1000000000000"),
        "KiB": Decimal("1024"),
        "MiB": Decimal("1048576"),
        "GiB": Decimal("1073741824"),
        "TiB": Decimal("1099511627776"),
    },
}

UNIT_NAMES: dict[str, dict[str, str]] = {
    "length": {
        "m": "metre",
        "km": "kilometre",
        "cm": "centimetre",
        "mm": "millimetre",
        "mi": "mile",
        "yd": "yard",
        "ft": "foot",
        "in": "inch",
        "nmi": "nautical mile",
    },
    "mass": {
        "kg": "kilogram",
        "g": "gram",
        "mg": "milligram",
        "t": "metric tonne",
        "lb": "pound",
        "oz": "ounce",
        "st": "stone",
    },
    "volume": {
        "l": "litre",
        "ml": "millilitre",
        "m3": "cubic metre",
        "gal": "US gallon",
        "qt": "US quart",
        "pt": "US pint",
        "cup": "US cup",
        "floz": "US fluid ounce",
        "tbsp": "tablespoon",
        "tsp": "teaspoon",
    },
    "area": {
        "m2": "square metre",
        "km2": "square kilometre",
        "cm2": "square centimetre",
        "ha": "hectare",
        "acre": "acre",
        "ft2": "square foot",
        "in2": "square inch",
        "mi2": "square mile",
    },
    "speed": {
        "m/s": "metres per second",
        "km/h": "kilometres per hour",
        "mph": "miles per hour",
        "knot": "knot",
        "ft/s": "feet per second",
    },
    "time": {
        "s": "second",
        "min": "minute",
        "h": "hour",
        "day": "day",
        "week": "week",
        "year": "Julian year (365.25 days)",
    },
    "data": {
        "B": "byte",
        "kB": "kilobyte (1000 B)",
        "MB": "megabyte (1000 kB)",
        "GB": "gigabyte (1000 MB)",
        "TB": "terabyte (1000 GB)",
        "KiB": "kibibyte (1024 B)",
        "MiB": "mebibyte (1024 KiB)",
        "GiB": "gibibyte (1024 MiB)",
        "TiB": "tebibyte (1024 GiB)",
    },
}

TEMPERATURE_UNITS: dict[str, str] = {
    "C": "Celsius",
    "F": "Fahrenheit",
    "K": "Kelvin",
    "R": "Rankine",
}

DEFAULT_RATES: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.79"),
    "JPY": Decimal("149.50"),
    "CAD": Decimal("1.36"),
    "AUD": Decimal("1.52"),
    "CHF": Decimal("0.88"),
    "CNY": Decimal("7.24"),
    "INR": Decimal("83.10"),
}

ALIASES: dict[str, dict[str, str]] = {
    "length": {
        "meter": "m", "meters": "m", "metre": "m", "metres": "m",
        "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km",
        "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
        "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
        "mile": "mi", "miles": "mi", "yard": "yd", "yards": "yd",
        "foot": "ft", "feet": "ft", "inch": "in", "inches": "in",
        "nautical mile": "nmi", "nautical miles": "nmi",
    },
    "mass": {
        "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g",
        "milligram": "mg", "milligrams": "mg", "tonne": "t", "tonnes": "t",
        "metric ton": "t", "metric tons": "t", "pound": "lb", "pounds": "lb",
        "ounce": "oz", "ounces": "oz", "stone": "st", "stones": "st",
    },
    "volume": {
        "liter": "l", "liters": "l", "litre": "l", "litres": "l",
        "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
        "cubic meter": "m3", "cubic meters": "m3", "cubic metre": "m3", "cubic metres": "m3",
        "gallon": "gal", "gallons": "gal", "quart": "qt", "quarts": "qt",
        "pint": "pt", "pints": "pt", "cup": "cup", "cups": "cup",
        "fluid ounce": "floz", "fluid ounces": "floz",
        "tablespoon": "tbsp", "tablespoons": "tbsp",
        "teaspoon": "tsp", "teaspoons": "tsp",
    },
    "area": {
        "square meter": "m2", "square meters": "m2", "square metre": "m2",
        "square metres": "m2", "square kilometer": "km2", "square kilometers": "km2",
        "square kilometre": "km2", "square kilometres": "km2",
        "square centimeter": "cm2", "square centimetre": "cm2",
        "hectare": "ha", "hectares": "ha", "acres": "acre",
        "square foot": "ft2", "square feet": "ft2", "square inch": "in2",
        "square inches": "in2", "square mile": "mi2", "square miles": "mi2",
    },
    "speed": {
        "meter per second": "m/s", "meters per second": "m/s",
        "metre per second": "m/s", "metres per second": "m/s",
        "kilometer per hour": "km/h", "kilometers per hour": "km/h",
        "kilometre per hour": "km/h", "kilometres per hour": "km/h",
        "kph": "km/h", "mile per hour": "mph", "miles per hour": "mph",
        "knots": "knot", "foot per second": "ft/s", "feet per second": "ft/s",
    },
    "time": {
        "second": "s", "seconds": "s", "sec": "s", "minute": "min", "minutes": "min",
        "hour": "h", "hours": "h", "day": "day", "days": "day",
        "week": "week", "weeks": "week", "year": "year", "years": "year",
    },
    "data": {
        "byte": "B", "bytes": "B", "kilobyte": "kB", "kilobytes": "kB",
        "megabyte": "MB", "megabytes": "MB", "gigabyte": "GB", "gigabytes": "GB",
        "terabyte": "TB", "terabytes": "TB", "kibibyte": "KiB", "kibibytes": "KiB",
        "mebibyte": "MiB", "mebibytes": "MiB", "gibibyte": "GiB", "gibibytes": "GiB",
        "tebibyte": "TiB", "tebibytes": "TiB",
    },
    "temperature": {
        "celsius": "C", "centigrade": "C", "fahrenheit": "F",
        "kelvin": "K", "rankine": "R",
    },
    "currency": {
        "dollar": "USD", "dollars": "USD", "us dollar": "USD", "us dollars": "USD",
        "euro": "EUR", "euros": "EUR", "pound sterling": "GBP",
        "british pound": "GBP", "yen": "JPY", "japanese yen": "JPY",
        "canadian dollar": "CAD", "australian dollar": "AUD",
        "swiss franc": "CHF", "yuan": "CNY", "renminbi": "CNY",
        "indian rupee": "INR", "rupee": "INR", "rupees": "INR",
    },
}
