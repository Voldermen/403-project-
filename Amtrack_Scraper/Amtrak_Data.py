"""Directly read Amtrak's official GTFS data, query train schedules locally, and output JSON.

Dependencies:
   python -m pip install gtfs-kit pandas

Usage:
   python Amtrak_GTFS_Local.py
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import gtfs_kit as gk
import pandas as pd

# Amtrak GTFS official download address
GTFS_URL = "https://content.amtrak.com/content/gtfs/GTFS.zip"

# Station code dictionary (partially excerpted from the GTFS stops.txt)
# Format: station code -> (city name, latitude, longitude)
# The "Name" field in the final output uses the station code
STATIONS = {
    "NYP": ("New York", 40.7527, -73.9772),
    "WAS": ("Washington", 38.8973, -77.0063),
    "BOS": ("Boston", 42.3512, -71.0552),
    "PHL": ("Philadelphia", 39.9557, -75.1820),
    "CHI": ("Chicago", 41.8789, -87.6394),
    "NOL": ("New Orleans", 29.9511, -90.0782),
    "LAX": ("Los Angeles", 34.0562, -118.2365),
    "SEA": ("Seattle", 47.5985, -122.3299),
    "POR": ("Portland", 45.5161, -122.6768),
    "DEN": ("Denver", 39.7530, -104.9996),
    "STL": ("St. Louis", 38.6270, -90.1994),
    "MEM": ("Memphis", 35.1495, -90.0490),
    # You can add more station codes according to the stops.txt in the GTFS
}


def check_station(code: str) -> str:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code) or code not in STATIONS:
        raise ValueError(f"Unknown station code: {code!r}. Try NYP, WAS, BOS, etc.")
    return code


def parse_search_date(text: str) -> date:
    text = text.strip()
    try:
        d = date.fromisoformat(text)
    except ValueError:
        d = datetime.strptime(text, "%m/%d/%Y").date()
    if d < date.today():
        raise ValueError("Search date must be today or in the future.")
    return d


def station_location(code: str) -> dict:
    city, lat, lon = STATIONS.get(code, (None, None, None))
    return {
        "City": city,
        "Name": code,
        "GPS": {"LAT": lat, "LONG": lon},
    }


def clock_time(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return f"{dt.hour}:{dt.minute:02d}"


def search_amtrak_gtfs(origin: str, destination: str, travel_date: date, limit: int = 5) -> dict:
    """Read GTFS locally, find trips between the two stations on the specified date."""
    # 1. Load feed (gtfs_kit will automatically download and parse)
    print("Loading Amtrak GTFS feed (first run may take a few seconds)...")
    feed = gk.read_feed(GTFS_URL, dist_units="km")

    # 2. Find the stop_ids for the two stations
    stops = feed.stops
    origin_rows = stops[stops.stop_id == origin]
    dest_rows = stops[stops.stop_id == destination]
    if origin_rows.empty or dest_rows.empty:
        raise ValueError("Origin or destination station not found in GTFS feed.")
    origin_stop_id = origin_rows.iloc[0]["stop_id"]
    dest_stop_id = dest_rows.iloc[0]["stop_id"]

    # Use gtfs_kit's built-in method to directly get trips for the specified date
    date_str = travel_date.strftime("%Y%m%d")
    trips_today = feed.get_trips(date=date_str)

    if trips_today.empty:
        print(f"No service active on {travel_date}.")
        return {"Rides": []}

    # 5. Find stop_times for these trips
    stop_times = feed.stop_times
    # Departure records at origin station
    dep_at_origin = stop_times[
        (stop_times.stop_id == origin_stop_id)
        & (stop_times.trip_id.isin(trips_today.trip_id))
    ]
    # Arrival records at destination station
    arr_at_dest = stop_times[
        (stop_times.stop_id == dest_stop_id)
        & (stop_times.trip_id.isin(trips_today.trip_id))
    ]

    if dep_at_origin.empty or arr_at_dest.empty:
        print(f"No direct trips found from {origin} to {destination} on {travel_date}.")
        return {"Rides": []}

    # 6. Match: same trip_id, and departure time < arrival time (ensure correct direction)
    # Note: GTFS times are strings like "08:30:00", need simple conversion for comparison
    def to_minutes(t: str) -> int:
        h, m, s = map(int, t.split(":"))
        return h * 60 + m

    results = []
    for _, dep in dep_at_origin.iterrows():
        # Find arrival records for the same trip at the destination station
        arr_candidates = arr_at_dest[arr_at_dest.trip_id == dep.trip_id]
        if arr_candidates.empty:
            continue
        arr = arr_candidates.iloc[0]
        dep_min = to_minutes(dep.departure_time)
        arr_min = to_minutes(arr.arrival_time)
        if arr_min <= dep_min:
            continue  # Wrong direction or overnight issue, skip

        # Parse times into datetime for output
        dep_dt = datetime.combine(travel_date, datetime.min.time()) + timedelta(minutes=dep_min)
        arr_dt = datetime.combine(travel_date, datetime.min.time()) + timedelta(minutes=arr_min)
        duration = arr_min - dep_min

        results.append({
            "dep_dt": dep_dt,
            "arr_dt": arr_dt,
            "duration": duration,
            "trip_id": dep.trip_id,
        })

    # 7. Sort by departure time
    results.sort(key=lambda x: x["dep_dt"])
    results = results[:limit]

    # 8. Build output JSON structure
    rides = []
    for rank, r in enumerate(results, start=1):
        rides.append({
            "Method": {
                "Type": "Rail",
                "Priority": rank,
                "Cost": None,  # GTFS has no fares
                "Travel Time (min)": r["duration"],
                "Departure": clock_time(r["dep_dt"]),
                "Arrival": clock_time(r["arr_dt"]),
                "Date": f"{travel_date.month}/{travel_date.day}/{travel_date.year}",
                "Staring Location": station_location(origin),
                "Destination": station_location(destination),
            }
        })

    return {"Rides": rides}


def main():
    try:
        print("Amtrak GTFS Local Search\n")
        origin = check_station(input("Starting station (e.g., NYP): "))
        dest = check_station(input("Destination station (e.g., WAS): "))
        if origin == dest:
            raise ValueError("Origin and destination must differ.")

        travel_date = parse_search_date(input("Travel date (YYYY-MM-DD): "))
        limit = int(input("Maximum results [5]: ").strip() or "5")

        result = search_amtrak_gtfs(origin, dest, travel_date, limit)

        output = Path("amtrak.json")
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\n" + json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\nSaved {len(result['Rides'])} result(s) to {output.resolve()}")

    except (ValueError, LookupError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Amtrak GTFS could not be read: {exc}", file=sys.stderr)
        print("The feed may have moved or the date range is not covered.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()