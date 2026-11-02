#!/usr/bin/env python3
"""Fetch Current Weather - current conditions and a multi-day forecast.

Uses the free Open-Meteo APIs (no API key): its geocoding endpoint turns a city
name or postal code into coordinates, and the forecast endpoint supplies current
conditions plus daily highs, lows and rain probability.  ``--demo`` renders
bundled sample JSON, so it works completely offline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "current-weather/1.0 (+stdlib)"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
POSTAL_URL = "https://api.zippopotam.us"
IP_LOCATE_URL = "https://ipapi.co/json/"
CURRENT_FIELDS = ("temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
                  "precipitation,weather_code,wind_speed_10m,wind_direction_10m")
DAILY_FIELDS = ("weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max")
SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "☀"), 1: ("Mainly clear", "🌤"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"), 45: ("Fog", "🌫"), 48: ("Depositing rime fog", "🌫"),
    51: ("Light drizzle", "🌦"), 53: ("Moderate drizzle", "🌦"),
    55: ("Dense drizzle", "🌧"), 56: ("Light freezing drizzle", "🌧"),
    57: ("Dense freezing drizzle", "🌧"), 61: ("Slight rain", "🌦"),
    63: ("Moderate rain", "🌧"), 65: ("Heavy rain", "🌧"),
    66: ("Light freezing rain", "🌧"), 67: ("Heavy freezing rain", "🌧"),
    71: ("Slight snow", "🌨"), 73: ("Moderate snow", "🌨"), 75: ("Heavy snow", "❄"),
    77: ("Snow grains", "🌨"), 80: ("Slight rain showers", "🌦"),
    81: ("Moderate rain showers", "🌧"), 82: ("Violent rain showers", "⛈"),
    85: ("Slight snow showers", "🌨"), 86: ("Heavy snow showers", "❄"),
    95: ("Thunderstorm", "⛈"), 96: ("Thunderstorm with slight hail", "⛈"),
    99: ("Thunderstorm with heavy hail", "⛈"),
}
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


class WeatherError(Exception):
    """Raised when a weather lookup cannot be completed."""


@dataclass
class Location:
    """A resolved place with coordinates."""

    name: str
    latitude: float
    longitude: float
    country: str = ""
    admin1: str = ""
    timezone: str = ""
    postal: str = ""

    def display_name(self) -> str:
        """Human-readable place label without duplicate components."""
        parts = [self.name]
        if self.admin1 and self.admin1.lower() != self.name.lower():
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        label = ", ".join(parts)
        return f"{label} ({self.postal})" if self.postal else label


def http_json(url: str, timeout: float) -> dict[str, Any]:
    """GET a JSON document with a clear error on network or HTTP failure."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000)
    except HTTPError as exc:
        reason = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            reason = payload.get("reason") or payload.get("error") or ""
        except (ValueError, UnicodeDecodeError):
            pass
        detail = f": {reason}" if reason else ""
        raise WeatherError(f"HTTP {exc.code} from {url.split('?')[0]}{detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WeatherError(f"network error contacting {url.split('?')[0]}: "
                           f"{getattr(exc, 'reason', exc)}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherError(f"invalid JSON from {url.split('?')[0]}") from exc
    if not isinstance(payload, dict):
        raise WeatherError(f"unexpected response from {url.split('?')[0]}")
    if payload.get("error"):
        raise WeatherError(str(payload.get("reason", "weather service error")))
    return payload


def geocode_city(name: str, country: str | None, timeout: float) -> Location:
    """Look up a city with the Open-Meteo geocoding API."""
    params: dict[str, str] = {"name": name, "count": "1", "language": "en", "format": "json"}
    if country:
        params["countryCode"] = country.upper()
    payload = http_json(f"{GEOCODE_URL}?{urlencode(params)}", timeout)
    results = payload.get("results") or []
    if not results:
        raise WeatherError(f"no place found for {name!r}"
                           + (f" in country {country.upper()}" if country else ""))
    hit = results[0]
    try:
        return Location(str(hit["name"]), float(hit["latitude"]), float(hit["longitude"]),
                        str(hit.get("country", "")), str(hit.get("admin1", "")),
                        str(hit.get("timezone", "")))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("geocoding response is missing coordinates") from exc


def geocode_postal(postal: str, country: str, timeout: float) -> Location:
    """Resolve a postal code with Zippopotam.us (no key required)."""
    payload = http_json(f"{POSTAL_URL}/{country.lower()}/{postal.strip()}", timeout)
    places = payload.get("places") or []
    if not places:
        raise WeatherError(f"postal code {postal!r} not found in {country.upper()}")
    place = places[0]
    try:
        latitude = float(place["latitude"])
        longitude = float(place["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("postal lookup returned no coordinates") from exc
    state = str(place.get("state", ""))
    short = str(place.get("state abbreviation", ""))
    name = str(place.get("place name", postal))
    return Location(name, latitude, longitude, str(payload.get("country", "")),
                    state, "", f"{short} {postal}".strip())


def locate_by_ip(timeout: float) -> Location:
    """Best-effort approximate location from the caller's public IP address."""
    payload = http_json(IP_LOCATE_URL, timeout)
    if payload.get("error"):
        raise WeatherError(str(payload.get("reason") or "IP geolocation failed"))
    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("IP geolocation returned no coordinates") from exc
    name = str(payload.get("city") or payload.get("region") or "Approximate location")
    return Location(name, latitude, longitude, str(payload.get("country_name", "")),
                    str(payload.get("region", "")), str(payload.get("timezone", "")))


def fetch_forecast(location: Location, units: str, days: int, timeout: float) -> dict[str, Any]:
    """Fetch current conditions and a daily forecast for ``location``."""
    params = {
        "latitude": f"{location.latitude:.4f}",
        "longitude": f"{location.longitude:.4f}",
        "current": CURRENT_FIELDS,
        "daily": DAILY_FIELDS,
        "timezone": "auto",
        "forecast_days": str(days),
    }
    if units == "imperial":
        params.update(temperature_unit="fahrenheit", wind_speed_unit="mph",
                      precipitation_unit="inch")
    payload = http_json(f"{FORECAST_URL}?{urlencode(params)}", timeout)
    if not isinstance(payload.get("current"), dict):
        raise WeatherError("forecast response contains no current conditions")
    return payload


def describe_code(code: Any) -> tuple[str, str]:
    """Return the label and symbol for a WMO weather code."""
    try:
        return WEATHER_CODES.get(int(code), ("Unknown conditions", "?"))
    except (TypeError, ValueError):
        return ("Unknown conditions", "?")


def compass_direction(degrees: Any) -> str:
    """Convert wind bearing in degrees to a 16-point compass direction."""
    try:
        value = float(degrees) % 360
    except (TypeError, ValueError):
        return "?"
    return COMPASS[int((value / 22.5) + 0.5) % 16]


def c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9 / 5 + 32


def kmh_to_mph(speed: float) -> float:
    """Convert kilometres per hour to miles per hour."""
    return speed * 0.621371


def render_report(location: Location, forecast: dict[str, Any], units: str) -> None:
    """Print a human-readable current-conditions and forecast report."""
    current = forecast.get("current", {})
    current_units = forecast.get("current_units", {})
    daily = forecast.get("daily", {})
    daily_units = forecast.get("daily_units", {})
    temp_unit = current_units.get("temperature_2m", "°F" if units == "imperial" else "°C")
    wind_unit = current_units.get("wind_speed_10m", "mph" if units == "imperial" else "km/h")
    if wind_unit in ("mp/h", "mph"):
        wind_unit = "mph"
    precip_unit = current_units.get("precipitation", "inch" if units == "imperial" else "mm")
    timezone_name = forecast.get("timezone", location.timezone) or "unknown"
    abbreviation = forecast.get("timezone_abbreviation", "")
    zone = f"{timezone_name}" + (f" ({abbreviation})" if abbreviation else "")

    print(f"Weather for {location.display_name()}")
    print(f"Location: {location.latitude:.4f}, {location.longitude:.4f} · timezone {zone}")
    print()
    code = current.get("weather_code")
    label, symbol = describe_code(code)
    observed = str(current.get("time", "unknown")).replace("T", " ")
    print(f"Current conditions — {observed} local")
    print(f"  {symbol}  {label} (WMO {code})")
    print(f"  Temperature:   {current.get('temperature_2m', 'n/a')} {temp_unit} "
          f"(feels like {current.get('apparent_temperature', 'n/a')} {temp_unit})")
    print(f"  Humidity:      {current.get('relative_humidity_2m', 'n/a')}%")
    print(f"  Wind:          {current.get('wind_speed_10m', 'n/a')} {wind_unit} from "
          f"{compass_direction(current.get('wind_direction_10m'))} "
          f"({current.get('wind_direction_10m', '?')}°)")
    print(f"  Precipitation: {current.get('precipitation', 'n/a')} {precip_unit}")
    print(f"  Daylight:      {'yes' if current.get('is_day') else 'no'}")

    times = daily.get("time") or []
    if not times:
        print("\nNo daily forecast returned.")
        return
    maxes = daily.get("temperature_2m_max") or []
    mins = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    rain = daily.get("precipitation_probability_max") or []
    daily_temp_unit = daily_units.get("temperature_2m_max", temp_unit)

    print(f"\n{len(times)}-day forecast:")
    print(f"  {'Day':<12} {'Condition':<26} {'Low … High':>18} {'Rain':>6}")
    print("  " + "-" * 66)
    for index, stamp in enumerate(times):
        try:
            day = date.fromisoformat(str(stamp))
            day_label = day.strftime("%a %d %b")
        except ValueError:
            day_label = str(stamp)
        condition, _symbol = describe_code(codes[index] if index < len(codes) else None)
        low = mins[index] if index < len(mins) else "?"
        high = maxes[index] if index < len(maxes) else "?"
        chance = rain[index] if index < len(rain) else "?"
        chance_text = f"{chance}%" if isinstance(chance, (int, float)) else "n/a"
        temp_text = f"{low} … {high} {daily_temp_unit}"
        print(f"  {day_label:<12} {condition:<26} {temp_text:>18} {chance_text:>6}")


def build_json(location: Location, forecast: dict[str, Any]) -> dict[str, Any]:
    """Build a compact machine-readable report."""
    return {
        "location": {
            "name": location.name,
            "admin1": location.admin1,
            "country": location.country,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": forecast.get("timezone", location.timezone),
        },
        "current": forecast.get("current", {}),
        "current_units": forecast.get("current_units", {}),
        "daily": forecast.get("daily", {}),
        "daily_units": forecast.get("daily_units", {}),
    }


def load_sample() -> tuple[Location, dict[str, Any]]:
    """Load the bundled Open-Meteo payloads used by the offline demo."""
    try:
        geocode = json.loads((SAMPLE_DIR / "geocode_boston.json").read_text(encoding="utf-8"))
        forecast = json.loads((SAMPLE_DIR / "forecast_boston.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeatherError(f"cannot read bundled sample data: {exc}") from exc
    hit = (geocode.get("results") or [{}])[0]
    try:
        location = Location(str(hit["name"]), float(hit["latitude"]), float(hit["longitude"]),
                            str(hit.get("country", "")), str(hit.get("admin1", "")),
                            str(hit.get("timezone", "")))
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("bundled geocoding sample is malformed") from exc
    return location, forecast


def run_lookup(args: argparse.Namespace) -> int:
    """Resolve a location, fetch the forecast and print it."""
    try:
        if args.auto_locate:
            location = locate_by_ip(args.timeout)
            if not args.json:
                print(f"Located approximately by IP: {location.display_name()}")
        else:
            query = args.location.strip()
            if args.postal or re.fullmatch(r"\d{5}(?:-\d{4})?", query):
                location = geocode_postal(query, (args.country or "us").upper(), args.timeout)
            else:
                location = geocode_city(query, args.country, args.timeout)
            if not args.json:
                print(f"Resolved {query!r} to {location.display_name()} "
                      f"({location.latitude:.3f}, {location.longitude:.3f})\n")
        forecast = fetch_forecast(location, args.units, args.days, args.timeout)
    except WeatherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(build_json(location, forecast), indent=2, ensure_ascii=False))
    else:
        render_report(location, forecast, args.units)
    return 0


# --------------------------------------------------------------------------- demo

def run_demo() -> int:
    """Render the bundled sample forecast without touching the network."""
    print("Fetch Current Weather demo (offline: bundled Open-Meteo sample JSON)\n")
    try:
        location, forecast = load_sample()
    except WeatherError as exc:
        print(f"demo error: {exc}", file=sys.stderr)
        return 1
    print(f"Sample data: {SAMPLE_DIR.name}/geocode_boston.json, "
          f"forecast_boston.json\n")
    render_report(location, forecast, "metric")

    current = forecast["current"]
    fahrenheit = c_to_f(float(current["temperature_2m"]))
    mph = kmh_to_mph(float(current["wind_speed_10m"]))
    print("\nUnit conversion check "
          f"(for --units imperial): {current['temperature_2m']} °C = {fahrenheit:.1f} °F; "
          f"{current['wind_speed_10m']} km/h = {mph:.1f} mph.")

    checks = [
        len(forecast["daily"]["time"]) == 5,
        len(forecast["daily"]["temperature_2m_max"]) == 5,
        abs(fahrenheit - 54.32) < 0.01,
    ]
    print(f"\nDemo complete: 5-day sample forecast rendered, all checks "
          f"{'passed' if all(checks) else 'FAILED'} (no network used).")
    return 0 if all(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Show current weather and a multi-day forecast for a city or postal code.",
        epilog="Examples:\n"
               "  python3 solution.py \"Boston, MA\"\n"
               "  python3 solution.py 90210\n"
               "  python3 solution.py 10115 --postal --country de --units metric\n"
               "  python3 solution.py --auto-locate --days 7\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("location", nargs="?", help="city name or postal code")
    parser.add_argument("--postal", action="store_true",
                        help="treat the location as a postal code (non-US codes need --country)")
    parser.add_argument("--country", help="ISO country code (for postal codes; optional city filter)")
    parser.add_argument("--units", choices=("metric", "imperial"), default="metric",
                        help="metric (°C, km/h, mm) or imperial (°F, mph, inch); default: metric")
    parser.add_argument("--days", type=int, default=5,
                        help="forecast days, 1-16 (default: 5)")
    parser.add_argument("--auto-locate", action="store_true",
                        help="approximate the location from the public IP address")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="HTTP timeout in seconds (default: 10)")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not 1 <= args.days <= 16:
        parser.error("--days must be between 1 and 16")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not args.location and not args.auto_locate:
        if not sys.stdin.isatty():
            parser.error("provide a city/postal code, use --auto-locate, or use --demo")
        try:
            args.location = input("City or postal code: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.location:
            print("error: no location entered", file=sys.stderr)
            return 2
    if args.location and not args.location.strip():
        print("error: empty location", file=sys.stderr)
        return 2
    return run_lookup(args)


if __name__ == "__main__":
    raise SystemExit(main())
