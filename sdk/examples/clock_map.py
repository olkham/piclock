#!/usr/bin/env python3
"""clock_map — Set your PiClock background to a map tile of any city.

Geocodes a city name, fetches a map tile from OpenStreetMap, uploads it
as the clock background, and sets the timezone to match the location.

Usage:
    python clock_map.py "New York City"
    python clock_map.py "Tokyo" --host 192.168.1.50 --zoom 12
    python clock_map.py "London" --host piclock.local --port 8080

Requirements:
    pip install piclock-sdk geopy
    (or: pip install ./sdk[examples])
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
import urllib.request
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

from piclock import PiClock


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode_city(city: str) -> tuple[float, float, str]:
    """Geocode a city name. Returns (lat, lon, display_name)."""
    geolocator = Nominatim(user_agent="piclock-clock-map/1.0")
    try:
        location = geolocator.geocode(city, timeout=10, language="en")
    except GeocoderTimedOut:
        print(f"Error: Geocoding timed out for '{city}'", file=sys.stderr)
        sys.exit(1)
    if not location:
        print(f"Error: Could not find location '{city}'", file=sys.stderr)
        sys.exit(1)
    return location.latitude, location.longitude, location.address


# ---------------------------------------------------------------------------
# Timezone lookup (via PiClock's own timezone list)
# ---------------------------------------------------------------------------

def find_timezone(clock: PiClock, lat: float, lon: float, city: str) -> str:
    """Find the best matching IANA timezone for a location.

    Strategy: search the PiClock's timezone list using the city name,
    then fall back to a longitude-based UTC offset estimate.
    """
    # Try searching by city keywords
    city_parts = city.replace(",", " ").split()
    for part in city_parts:
        if len(part) < 3:
            continue
        results = clock.list_timezones(query=part)
        if results:
            return results[0]["name"]

    # Fallback: estimate timezone from longitude (rough but universal)
    offset_hours = round(lon / 15)
    sign = "+" if offset_hours >= 0 else "-"
    etc_tz = f"Etc/GMT{'+' if offset_hours <= 0 else '-'}{abs(offset_hours)}"
    # Etc/GMT uses inverted signs — try exact match
    results = clock.list_timezones(query=etc_tz)
    if results:
        return results[0]["name"]

    # Last resort
    return "UTC"


# ---------------------------------------------------------------------------
# Map tile fetching (OpenStreetMap)
# ---------------------------------------------------------------------------

def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to OSM tile coordinates at a given zoom level."""
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


def fetch_map_tile(lat: float, lon: float, zoom: int = 13) -> Path:
    """Fetch an OSM map tile and save to a temp file. Returns the path."""
    x, y = lat_lon_to_tile(lat, lon, zoom)
    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={
        "User-Agent": "piclock-clock-map/1.0 (https://github.com/olkham/piclock)"
    })

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tmp.write(resp.read())
        tmp.close()
        return Path(tmp.name)
    except Exception as exc:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        print(f"Error fetching map tile: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Set your PiClock to display a map tile and timezone for any city."
    )
    parser.add_argument("city", help="City name (e.g. 'New York City', 'Tokyo', 'London')")
    parser.add_argument("--host", default="localhost", help="PiClock hostname/IP (default: localhost)")
    parser.add_argument("--port", type=int, default=8080, help="PiClock web port (default: 8080)")
    parser.add_argument("--zoom", type=int, default=13, help="Map zoom level 1-18 (default: 13)")
    parser.add_argument("--theme", default=None, help="Theme to update (default: active theme)")
    args = parser.parse_args()

    clock = PiClock(host=args.host, port=args.port)

    # 1. Geocode the city
    print(f"Geocoding '{args.city}'...")
    lat, lon, display_name = geocode_city(args.city)
    print(f"  Found: {display_name}")
    print(f"  Coordinates: {lat:.4f}, {lon:.4f}")

    # 2. Find and set the timezone
    print("Setting timezone...")
    tz = find_timezone(clock, lat, lon, args.city)
    clock.set_timezone(tz)
    print(f"  Timezone: {tz}")

    # 3. Fetch the map tile
    print(f"Fetching map tile (zoom {args.zoom})...")
    tile_path = fetch_map_tile(lat, lon, args.zoom)
    print(f"  Downloaded: {tile_path}")

    # 4. Set as background
    print("Uploading background image...")
    clock.set_background_image(tile_path, theme=args.theme)
    tile_path.unlink(missing_ok=True)  # clean up temp file

    print(f"\nDone! Your PiClock now shows {args.city} ({tz}).")


if __name__ == "__main__":
    main()
