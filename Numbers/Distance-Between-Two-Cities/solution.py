#!/usr/bin/env python3
"""Great-circle distance between two cities.

Distances come from an embedded gazetteer of 60+ world cities (latitude and
longitude), so the program works completely offline.  An optional
``--geocode`` flag queries OpenStreetMap's Nominatim service for cities that
are not in the table; if the network is unavailable the program reports the
problem and falls back to the offline table.

Examples:
    python3 solution.py --from London --to Tokyo
    python3 solution.py --from "New York" --to "San Francisco" --unit mi
    python3 solution.py --list-cities
    python3 solution.py --demo
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import sys
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EARTH_RADIUS_KM = 6371.0088

UNITS: dict[str, tuple[str, float]] = {
    "km": ("kilometres", 1.0),
    "mi": ("miles", 0.621371192237334),
    "nmi": ("nautical miles", 0.539956803455724),
    "m": ("metres", 1000.0),
    "ft": ("feet", 3280.839895013123),
}


@dataclass(frozen=True)
class City:
    """A city with coordinates and optional country metadata."""

    name: str
    country: str
    lat: float
    lon: float


def _city(name: str, country: str, lat: float, lon: float,
          *aliases: str) -> tuple[City, tuple[str, ...]]:
    return City(name, country, lat, lon), aliases


_RAW_CITIES = [
    _city("London", "United Kingdom", 51.5074, -0.1278, "london uk"),
    _city("Paris", "France", 48.8566, 2.3522),
    _city("Berlin", "Germany", 52.5200, 13.4050),
    _city("Madrid", "Spain", 40.4168, -3.7038),
    _city("Rome", "Italy", 41.9028, 12.4964),
    _city("Lisbon", "Portugal", 38.7223, -9.1393),
    _city("Amsterdam", "Netherlands", 52.3676, 4.9041),
    _city("Brussels", "Belgium", 50.8503, 4.3517),
    _city("Vienna", "Austria", 48.2082, 16.3738),
    _city("Zurich", "Switzerland", 47.3769, 8.5417, "zuerich"),
    _city("Prague", "Czechia", 50.0755, 14.4378),
    _city("Warsaw", "Poland", 52.2297, 21.0122),
    _city("Budapest", "Hungary", 47.4979, 19.0402),
    _city("Copenhagen", "Denmark", 55.6761, 12.5683),
    _city("Stockholm", "Sweden", 59.3293, 18.0686),
    _city("Oslo", "Norway", 59.9139, 10.7522),
    _city("Helsinki", "Finland", 60.1699, 24.9384),
    _city("Dublin", "Ireland", 53.3498, -6.2603),
    _city("Athens", "Greece", 37.9838, 23.7275),
    _city("Istanbul", "Turkey", 41.0082, 28.9784),
    _city("Moscow", "Russia", 55.7558, 37.6173),
    _city("Kyiv", "Ukraine", 50.4501, 30.5234, "kiev"),
    _city("Reykjavik", "Iceland", 64.1466, -21.9426),
    _city("New York", "United States", 40.7128, -74.0060, "nyc", "new york city"),
    _city("Los Angeles", "United States", 34.0522, -118.2437, "la"),
    _city("Chicago", "United States", 41.8781, -87.6298),
    _city("San Francisco", "United States", 37.7749, -122.4194, "sf"),
    _city("Seattle", "United States", 47.6062, -122.3321),
    _city("Boston", "United States", 42.3601, -71.0589),
    _city("Washington", "United States", 38.9072, -77.0369, "washington dc", "dc"),
    _city("Miami", "United States", 25.7617, -80.1918),
    _city("Anchorage", "United States", 61.2181, -149.9003),
    _city("Honolulu", "United States", 21.3069, -157.8583),
    _city("Toronto", "Canada", 43.6532, -79.3832),
    _city("Vancouver", "Canada", 49.2827, -123.1207),
    _city("Montreal", "Canada", 45.5017, -73.5673),
    _city("Mexico City", "Mexico", 19.4326, -99.1332, "cdmx"),
    _city("Sao Paulo", "Brazil", -23.5505, -46.6333, "são paulo"),
    _city("Rio de Janeiro", "Brazil", -22.9068, -43.1729, "rio"),
    _city("Buenos Aires", "Argentina", -34.6037, -58.3816),
    _city("Lima", "Peru", -12.0464, -77.0428),
    _city("Santiago", "Chile", -33.4489, -70.6693),
    _city("Bogota", "Colombia", 4.7110, -74.0721, "bogotá"),
    _city("Cairo", "Egypt", 30.0444, 31.2357),
    _city("Lagos", "Nigeria", 6.5244, 3.3792),
    _city("Nairobi", "Kenya", -1.2921, 36.8219),
    _city("Johannesburg", "South Africa", -26.2041, 28.0473),
    _city("Cape Town", "South Africa", -33.9249, 18.4241),
    _city("Casablanca", "Morocco", 33.5731, -7.5898),
    _city("Dubai", "United Arab Emirates", 25.2048, 55.2708),
    _city("Mumbai", "India", 19.0760, 72.8777, "bombay"),
    _city("Delhi", "India", 28.6139, 77.2090, "new delhi"),
    _city("Bangalore", "India", 12.9716, 77.5946, "bengaluru"),
    _city("Bangkok", "Thailand", 13.7563, 100.5018),
    _city("Singapore", "Singapore", 1.3521, 103.8198),
    _city("Kuala Lumpur", "Malaysia", 3.1390, 101.6869, "kl"),
    _city("Jakarta", "Indonesia", -6.2088, 106.8456),
    _city("Hong Kong", "China", 22.3193, 114.1694),
    _city("Shanghai", "China", 31.2304, 121.4737),
    _city("Beijing", "China", 39.9042, 116.4074),
    _city("Tokyo", "Japan", 35.6762, 139.6503),
    _city("Seoul", "South Korea", 37.5665, 126.9780),
    _city("Sydney", "Australia", -33.8688, 151.2093),
    _city("Melbourne", "Australia", -37.8136, 144.9631),
    _city("Auckland", "New Zealand", -36.8485, 174.7633),
]

CITIES: dict[str, City] = {city.name: city for city, _ in _RAW_CITIES}


def normalise(text: str) -> str:
    """Case-fold and strip accents/punctuation for forgiving lookups."""

    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in ascii_text)
    return " ".join(cleaned.casefold().split())


_ALIASES = {}
for _city_obj, _city_aliases in _RAW_CITIES:
    _ALIASES[normalise(_city_obj.name)] = _city_obj.name
    for _alias in _city_aliases:
        _ALIASES[normalise(_alias)] = _city_obj.name
_ALIASES.update({"washington dc": "Washington", "new york city": "New York"})


def find_city(name: str) -> City | None:
    """Look up a city in the embedded gazetteer."""

    return CITIES.get(_ALIASES.get(normalise(name), ""))


def suggest_cities(name: str, limit: int = 3) -> list[str]:
    """Return close spelling suggestions from the gazetteer."""

    matches = difflib.get_close_matches(normalise(name), list(_ALIASES), n=limit * 2, cutoff=0.6)
    return list(dict.fromkeys(_ALIASES[match] for match in matches))[:limit]


def haversine_km(a: City, b: City) -> float:
    """Great-circle distance in kilometres using the haversine formula."""

    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dphi = phi2 - phi1
    dlambda = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


def initial_bearing(a: City, b: City) -> float:
    """Initial compass bearing from ``a`` to ``b`` in degrees (0 = north)."""

    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dlambda = math.radians(b.lon - a.lon)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def convert(km: float, unit: str) -> float:
    """Convert kilometres into the requested unit."""

    return km * UNITS[unit][1]


def geocode_nominatim(name: str, timeout: float = 5.0) -> City | None:
    """Look a city up online via Nominatim; return ``None`` on any failure."""

    query = urlencode({"q": name, "format": "jsonv2", "limit": 1})
    request = Request(
        f"https://nominatim.openstreetmap.org/search?{query}",
        headers={"User-Agent": "distance-between-two-cities/1.0 (learning project)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed host
            payload = json.load(response)
        if not payload:
            print(f"[geocode] no result for {name!r}", file=sys.stderr)
            return None
        hit = payload[0]
        label = hit.get("display_name", name).split(",")[0]
        return City(label, hit.get("display_name", "").split(",")[-1].strip(),
                    float(hit["lat"]), float(hit["lon"]))
    except Exception as exc:  # network, JSON, or key errors must not crash the program
        print(f"[geocode] offline or unavailable ({exc}); using the offline table.",
              file=sys.stderr)
        return None


def resolve_city(name: str, allow_network: bool) -> City:
    """Resolve a city name, optionally falling back to Nominatim."""

    city = find_city(name)
    if city:
        return city
    if allow_network:
        city = geocode_nominatim(name)
        if city:
            return city
    suggestions = suggest_cities(name)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise LookupError(f"unknown city {name!r}.{hint} Try --list-cities.")


def format_distance(value: float, unit: str) -> str:
    """Human-readable distance with sensible precision."""

    if unit in ("m", "ft"):
        return f"{value:,.0f} {unit}"
    return f"{value:,.2f} {unit}"


def print_route(a: City, b: City, unit: str) -> None:
    """Print distance and bearing for a city pair."""

    km = haversine_km(a, b)
    value = convert(km, unit)
    bearing = initial_bearing(a, b)
    print(f"{a.name} ({a.country}) -> {b.name} ({b.country})")
    print(f"  distance: {format_distance(value, unit)}")
    if unit != "km":
        print(f"            ({format_distance(km, 'km')} great-circle)")
    print(f"  initial bearing: {bearing:.1f} deg")


def run_demo() -> int:
    """Compare several well-known city pairs offline."""

    print("Distance Between Two Cities demo")
    print(f"Offline gazetteer: {len(CITIES)} cities")
    print("-" * 58)
    pairs = [
        ("London", "Paris", "km"),
        ("New York", "Los Angeles", "mi"),
        ("Tokyo", "Sydney", "km"),
        ("Cape Town", "Cairo", "nmi"),
    ]
    for origin, destination, unit in pairs:
        print_route(resolve_city(origin, False), resolve_city(destination, False), unit)
        print()
    print("Unit conversions for London -> Paris:")
    london, paris = CITIES["London"], CITIES["Paris"]
    for unit in UNITS:
        print(f"  {format_distance(convert(haversine_km(london, paris), unit), unit)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate the great-circle distance between two cities.",
        epilog="The built-in gazetteer works offline; --geocode adds a network lookup.",
    )
    parser.add_argument("--from", dest="origin", metavar="CITY", help="starting city")
    parser.add_argument("--to", dest="destination", metavar="CITY", help="destination city")
    parser.add_argument("--unit", choices=sorted(UNITS), default="km",
                        help="distance unit (default: km)")
    parser.add_argument("--geocode", action="store_true",
                        help="query Nominatim for cities missing from the offline table")
    parser.add_argument("--list-cities", action="store_true",
                        help="list every city in the offline gazetteer")
    parser.add_argument("--demo", action="store_true",
                        help="run a scripted offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.list_cities:
        print(f"{len(CITIES)} cities in the offline gazetteer:\n")
        for name in sorted(CITIES):
            city = CITIES[name]
            print(f"  {name:<15} {city.country:<22} {city.lat:8.4f}, {city.lon:9.4f}")
        return 0

    origin_name, destination_name = args.origin, args.destination
    if not origin_name:
        try:
            origin_name = input("From city: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
    if not destination_name:
        try:
            destination_name = input("To city: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0

    try:
        origin = resolve_city(origin_name, args.geocode)
        destination = resolve_city(destination_name, args.geocode)
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_route(origin, destination, args.unit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
