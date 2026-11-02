#!/usr/bin/env python3
"""Tax calculator for US states and countries.

Enter a net (pre-tax) amount and a region; the program looks up a built-in
base rate and prints the tax and the gross total.  Rates can be overridden
with ``--rate`` and tax-inclusive amounts can be split with ``--inclusive``.

Base rates only: US local/county taxes and country-specific reduced rates
are not modelled.  Use ``--rate`` for an exact local figure.

Examples:
    python3 solution.py --amount 100 --region california
    python3 solution.py --amount 250 --region UK
    python3 solution.py --amount 99.99 --region germany --inclusive
    python3 solution.py --list --kind country
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Region:
    """A tax jurisdiction and its base rate in percent."""

    name: str
    kind: str          # "state" or "country"
    rate: Decimal


def _state(name: str, rate: str, *aliases: str) -> tuple[Region, tuple[str, ...]]:
    return Region(name, "state", Decimal(rate)), aliases


def _country(name: str, rate: str, *aliases: str) -> tuple[Region, tuple[str, ...]]:
    return Region(name, "country", Decimal(rate)), aliases


_RAW_REGIONS = [
    _state("Alabama", "4.0", "al"),
    _state("Alaska", "0.0", "ak"),
    _state("Arizona", "5.6", "az"),
    _state("Arkansas", "6.5", "ar"),
    _state("California", "7.25", "ca", "calif"),
    _state("Colorado", "2.9", "co"),
    _state("Connecticut", "6.35", "ct"),
    _state("Delaware", "0.0", "de"),
    _state("Florida", "6.0", "fl"),
    _state("Georgia", "4.0", "ga"),
    _state("Hawaii", "4.0", "hi"),
    _state("Idaho", "6.0", "id"),
    _state("Illinois", "6.25", "il"),
    _state("Indiana", "7.0", "in"),
    _state("Iowa", "6.0", "ia"),
    _state("Kansas", "6.5", "ks"),
    _state("Kentucky", "6.0", "ky"),
    _state("Louisiana", "4.45", "la"),
    _state("Maine", "5.5", "me"),
    _state("Maryland", "6.0", "md"),
    _state("Massachusetts", "6.25", "ma"),
    _state("Michigan", "6.0", "mi"),
    _state("Minnesota", "6.875", "mn"),
    _state("Mississippi", "7.0", "ms"),
    _state("Missouri", "4.225", "mo"),
    _state("Montana", "0.0", "mt"),
    _state("Nebraska", "5.5", "ne"),
    _state("Nevada", "6.85", "nv"),
    _state("New Hampshire", "0.0", "nh"),
    _state("New Jersey", "6.625", "nj"),
    _state("New Mexico", "4.875", "nm"),
    _state("New York", "4.0", "ny"),
    _state("North Carolina", "4.75", "nc"),
    _state("North Dakota", "5.0", "nd"),
    _state("Ohio", "5.75", "oh"),
    _state("Oklahoma", "4.5", "ok"),
    _state("Oregon", "0.0", "or"),
    _state("Pennsylvania", "6.0", "pa"),
    _state("Rhode Island", "7.0", "ri"),
    _state("South Carolina", "6.0", "sc"),
    _state("South Dakota", "4.2", "sd"),
    _state("Tennessee", "7.0", "tn"),
    _state("Texas", "6.25", "tx"),
    _state("Utah", "6.1", "ut"),
    _state("Vermont", "6.0", "vt"),
    _state("Virginia", "5.3", "va"),
    _state("Washington", "6.5", "wa"),
    _state("West Virginia", "6.0", "wv"),
    _state("Wisconsin", "5.0", "wi"),
    _state("Wyoming", "4.0", "wy"),
    _state("District of Columbia", "6.0", "dc", "washington dc"),
    _country("United Kingdom", "20", "uk", "gb", "great britain", "england"),
    _country("Germany", "19", "de", "deutschland"),
    _country("France", "20", "fr"),
    _country("Spain", "21", "es"),
    _country("Italy", "22", "it"),
    _country("Netherlands", "21", "nl", "holland"),
    _country("Belgium", "21", "be"),
    _country("Austria", "20", "at"),
    _country("Switzerland", "8.1", "ch"),
    _country("Sweden", "25", "se"),
    _country("Norway", "25", "no"),
    _country("Denmark", "25", "dk"),
    _country("Finland", "24", "fi"),
    _country("Ireland", "23", "ie"),
    _country("Portugal", "23", "pt"),
    _country("Poland", "23", "pl"),
    _country("Czechia", "21", "cz", "czech republic"),
    _country("Hungary", "27", "hu"),
    _country("Romania", "19", "ro"),
    _country("Bulgaria", "20", "bg"),
    _country("Greece", "24", "gr"),
    _country("Croatia", "25", "hr"),
    _country("Slovakia", "20", "sk"),
    _country("Slovenia", "22", "si"),
    _country("Estonia", "22", "ee"),
    _country("Latvia", "21", "lv"),
    _country("Lithuania", "21", "lt"),
    _country("Luxembourg", "17", "lu"),
    _country("Malta", "18", "mt"),
    _country("Cyprus", "19", "cy"),
    _country("Turkey", "20", "tr", "turkiye"),
    _country("Russia", "20", "ru"),
    _country("Ukraine", "20", "ua"),
    _country("Japan", "10", "jp"),
    _country("South Korea", "10", "kr", "korea"),
    _country("China", "13", "cn"),
    _country("India", "18", "in"),
    _country("Australia", "10", "au"),
    _country("New Zealand", "15", "nz"),
    _country("Canada", "5", "ca canada", "gst"),
    _country("Mexico", "16", "mx"),
    _country("Brazil", "17", "br"),
    _country("Argentina", "21", "ar"),
    _country("Chile", "19", "cl"),
    _country("Colombia", "19", "co colombia"),
    _country("South Africa", "15", "za"),
    _country("Nigeria", "7.5", "ng"),
    _country("Kenya", "16", "ke"),
    _country("Egypt", "14", "eg"),
    _country("Israel", "17", "il"),
    _country("United Arab Emirates", "5", "uae", "ae"),
    _country("Saudi Arabia", "15", "sa"),
    _country("Singapore", "9", "sg"),
    _country("Indonesia", "11", "id"),
    _country("Malaysia", "6", "my"),
    _country("Thailand", "7", "th"),
    _country("Philippines", "12", "ph"),
    _country("Vietnam", "10", "vn"),
]

REGIONS: dict[str, Region] = {region.name.casefold(): region for region, _ in _RAW_REGIONS}
_ALIASES: dict[str, list[str]] = {}
for _region, _aliases in _RAW_REGIONS:
    _ALIASES.setdefault(_region.name.casefold(), []).append(_region.name.casefold())
    for _alias in _aliases:
        _ALIASES.setdefault(_alias.casefold(), []).append(_region.name.casefold())
for _ambiguous in ("us", "usa", "united states", "vat", "uk vat"):
    _ALIASES.pop(_ambiguous, None)
_ALIASES["washington dc"] = ["district of columbia"]


def normalise_region(text: str) -> str:
    """Normalise a region name: lowercase, collapse spaces, drop 'state of'."""

    cleaned = " ".join(text.strip().casefold().replace("_", " ").replace("-", " ").split())
    for prefix in ("state of ", "the "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned


def find_region(text: str) -> Region:
    """Resolve a state/country name or alias, reporting ambiguous codes."""

    key = normalise_region(text)
    if key.startswith("us "):
        key = key[3:]
    candidates = _ALIASES.get(key, [])
    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return REGIONS[unique[0]]
    if len(unique) > 1:
        options = ", ".join(f"{REGIONS[name].name} ({REGIONS[name].kind})" for name in unique)
        raise LookupError(f"{text!r} is ambiguous: {options}. Spell the name out.")
    raise LookupError(f"unknown region {text!r}; use --list to see supported regions")


def parse_amount(text: str) -> Decimal:
    """Parse a money amount, allowing currency symbols, commas and underscores."""

    cleaned = text.strip().replace(",", "").replace("_", "")
    for symbol in "$€£¥":
        cleaned = cleaned.replace(symbol, "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount {text!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be a non-negative finite number")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_tax(amount: Decimal, rate_percent: Decimal,
                inclusive: bool) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(net, tax, gross)`` for an amount and percentage rate."""

    rate = rate_percent / Decimal(100)
    if inclusive:
        net = (amount / (Decimal(1) + rate)).quantize(CENT, rounding=ROUND_HALF_UP)
        tax = (amount - net).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = amount
    else:
        net = amount
        tax = (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = (amount + tax).quantize(CENT, rounding=ROUND_HALF_UP)
    return net, tax, gross


def money(value: Decimal) -> str:
    """Format a Decimal as a plain two-decimal amount."""

    return f"{value:,.2f}"


def print_breakdown(region: Region, amount: Decimal, rate: Decimal,
                    inclusive: bool) -> None:
    """Print a readable tax breakdown."""

    net, tax, gross = compute_tax(amount, rate, inclusive)
    label = f"{region.name} ({region.kind})"
    print(f"Region:    {label}")
    print(f"Rate:      {rate.normalize():f}%")
    print(f"Net:       {money(net)}")
    print(f"Tax:       {money(tax)}")
    print(f"Total:     {money(gross)}")
    if inclusive:
        print("(amount treated as tax-inclusive)")


def run_demo() -> int:
    """Show typical state, country and inclusive calculations."""

    print("Tax Calculator demo")
    print("=" * 52)
    cases = [
        ("california", "100.00", None, False),
        ("texas", "249.99", None, False),
        ("UK", "250.00", None, False),
        ("germany", "99.99", None, True),
        ("new york", "80.00", "8.875", False),
    ]
    for region_name, amount_text, rate_text, inclusive in cases:
        region = find_region(region_name)
        rate = Decimal(rate_text) if rate_text else region.rate
        print_breakdown(region, parse_amount(amount_text), rate, inclusive)
        print()

    print(f"{len(REGIONS)} jurisdictions available "
          f"({sum(1 for r in REGIONS.values() if r.kind == 'state')} state-level, "
          f"{sum(1 for r in REGIONS.values() if r.kind == 'country')} countries).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate tax and total cost for a US state or country.",
        epilog="Rates are base rates; override with --rate for local taxes.",
    )
    parser.add_argument("-a", "--amount", metavar="COST", help="net cost, e.g. 100 or $99.99")
    parser.add_argument("-r", "--region", metavar="REGION",
                        help="US state or country, e.g. california, TX, UK, germany")
    parser.add_argument("--rate", metavar="PERCENT",
                        help="override the tax rate in percent, e.g. 8.875")
    parser.add_argument("--inclusive", action="store_true",
                        help="treat --amount as tax-inclusive and extract the tax")
    parser.add_argument("--kind", choices=("state", "country"), help="filter --list by kind")
    parser.add_argument("--list", action="store_true", help="list supported regions and rates")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.list:
        regions = sorted(REGIONS.values(), key=lambda region: (region.kind, region.name))
        if args.kind:
            regions = [region for region in regions if region.kind == args.kind]
        for region in regions:
            print(f"{region.kind:<8} {region.name:<24} {region.rate.normalize():>6f}%")
        return 0

    amount_text, region_text = args.amount, args.region
    if not amount_text:
        try:
            amount_text = input("Cost: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
    if not region_text:
        try:
            region_text = input("State or country: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0

    try:
        amount = parse_amount(amount_text)
        region = find_region(region_text)
        rate = Decimal(args.rate.rstrip("%").strip()) if args.rate else region.rate
        if not rate.is_finite() or rate < 0:
            raise ValueError("tax rate must be a non-negative number")
    except (ValueError, InvalidOperation, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_breakdown(region, amount, rate, args.inclusive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
