"""Search Google Flights and turn flight listings into JSON for our project.

Install the dependencies once:
   python -m pip install fast-flights airportsdata typing_extensions (enter this into CMD) 

Run it as an interactive command-line program:
    python google_flights_scraper.py

Other Python files can also import and call search_flights() directly.

NOTE: fast-flights is an unofficial scraper, NOT a Google Flights API.
The website may change, block automated searches, or return incomplete data.
"""

# json: turn the results (Python dictionaries/lists) into JSON text.
# re: check the format of airport codes (for example, "MSY").
# sys: display errors and exit with an error code when necessary.
import json
import re
import sys

# date/datetime: read and validate travel dates and flight times.
# timezone: compare times from airports in different time zones fairly.
from datetime import date, datetime, timezone

# Path: write the final JSON output to a file.
from pathlib import Path

# ZoneInfo: use an airport's real time zone, including daylight saving time.
from zoneinfo import ZoneInfo

# airportsdata: a database of airport codes, cities, GPS coordinates, and time zones.
import airportsdata

# fast_flights: build a search and retrieve flight itineraries from Google Flights.
from fast_flights import FlightQuery, Passengers, create_query, get_flights

# Load the airport database once when the Python module is imported.
# "IATA" means the three-letter airport codes (MSY, MCO, ORD, etc.).
AIRPORTS = airportsdata.load("IATA")


def parse_search_date(text: str) -> date:
    """Turn a typed date into a date object, rejecting dates in the past."""
    # Remove leading/trailing spaces from the user's input.
    text = text.strip()
    try:
        # First, try the standard format: YYYY-MM-DD (e.g., 2026-11-16).
        travel_date = date.fromisoformat(text)
    except ValueError:
        # If the first format failed, try M/D/YYYY (e.g., 11/16/2026).
        # A bad date in BOTH formats raises ValueError to the caller.
        travel_date = datetime.strptime(text, "%m/%d/%Y").date()

    # Searching for bookable flights in the past is not useful here.
    if travel_date < date.today():
        raise ValueError("Google Flights searches must use today's date or a future date.")
    return travel_date


def check_airport(code: str) -> str:
    """Validate and standardize a three-letter airport code."""
    # Convert inputs like " msy " into the standard "MSY".
    code = code.strip().upper()

    # [A-Z]{3}: exactly three uppercase letters.
    # "code not in AIRPORTS": confirm the airport exists in the database.
    if not re.fullmatch(r"[A-Z]{3}", code) or code not in AIRPORTS:
        raise ValueError(f"Unknown airport code: {code!r}. Enter an IATA code such as MSY or ORD.")
    return code


def airport_location(code: str) -> dict:
    """Build the city/code/GPS section of our required JSON format."""
    # Look up the airport; use an empty dictionary if information is missing.
    info = AIRPORTS.get(code, {})

    # Keys on the left (City, Name, GPS) match our project's JSON format.
    # Keys in info (city, lat, lon) come from the airportsdata library.
    return {
        "City": info.get("city"),
        "Name": code,
        "GPS": {"LAT": info.get("lat"), "LONG": info.get("lon")},
    }


def time_parts(value) -> tuple[int, int]:
    """Read a flight timestamp's hour and minute from fast_flights."""
    # The library may omit time components that are zero, so handle short lists.
    raw = list(value.time or [])
    return (int(raw[0] or 0) if len(raw) > 0 else 0,
            int(raw[1] or 0) if len(raw) > 1 else 0)


def local_datetime(value, airport_code: str) -> datetime | None:
    """Combine flight date/time with the airport's local time zone."""
    # Example: MSY's zone is America/Chicago; MCO's is America/New_York.
    timezone_name = AIRPORTS.get(airport_code, {}).get("tz")
    if not timezone_name:
        # Without a time zone, calculating elapsed time may be inaccurate.
        return None

    # fast_flights supplies the date separately from the local clock time.
    year, month, day = value.date
    hour, minute = time_parts(value)

    # ZoneInfo attaches the correct time-zone rules to that local clock time.
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(timezone_name))


def elapsed_minutes(first, last) -> int | None:
    """Get total travel time, including layovers and time-zone differences."""
    # Use the FIRST departure and the LAST arrival. For a connecting flight,
    # this includes waiting between flights, not just time in the air.
    departure = local_datetime(first.departure, first.from_airport.code)
    arrival = local_datetime(last.arrival, last.to_airport.code)

    if departure is None or arrival is None:
        return None

    # Convert BOTH times to UTC before subtracting. Otherwise, an MSY -> MCO
    # flight would appear one hour longer because Orlando is an hour ahead.
    minutes = round((arrival.astimezone(timezone.utc) - departure.astimezone(timezone.utc)).total_seconds() / 60)

    # If source dates/times are inconsistent, don't return a negative duration.
    return minutes if minutes >= 0 else None


def clock_time(value) -> str:
    """Format a 24-hour time as 12-hour local time (e.g., '3:05 PM')."""
    hour, minute = time_parts(value)
    period = "AM" if hour < 12 else "PM"

    # 15 % 12 = 3, giving 3 PM. "or 12" handles midnight/noon.
    twelve_hour = hour % 12 or 12
    # :02d prints minutes with two digits: 3:05 instead of 3:5.
    return f"{twelve_hour}:{minute:02d} {period}"


def itinerary_to_json(itinerary, priority: int) -> dict:
    """Convert ONE itinerary returned by fast_flights into our JSON schema."""
    # An itinerary can have one direct flight or multiple connecting flights.
    legs = itinerary.flights
    first, last = legs[0], legs[-1]
    year, month, day = first.departure.date

    # Calculate the entire trip's duration (including time spent on layovers).
    duration = elapsed_minutes(first, last)
    if duration is None and len(legs) == 1:
        # If time-zone data is missing for a DIRECT flight, use the duration
        # provided by fast_flights instead.
        duration = first.duration

    # Return a Python dictionary. json.dumps() converts it into actual JSON.
    return {
        "Method": {
            "Type": "Air",  # Our application also handles other transport types.
            "Priority": priority,  # Price rank: 1 = cheapest retrieved result.
            "Cost": itinerary.price,  # Price supplied by scraper in USD; not independently verified.
            "Travel Time (min)": duration,
            "Departure": clock_time(first.departure),  # First airport's local time.
            "Arrival": clock_time(last.arrival),  # Destination airport's local time.
            "Date": f"{month}/{day}/{year}",
            # Keep the original JSON field spelling for compatibility.
            "Staring Location": airport_location(first.from_airport.code),
            "Destination": {"Location": airport_location(last.to_airport.code)},
            "Airlines": itinerary.airlines,  # Airlines associated with this itinerary.
            "Stops": len(legs) - 1,  # Two flight legs = one stop/connection.
        }
    }


def search_flights(origin: str, destination: str, travel_date: date, adults: int = 1, limit: int = 5) -> dict:
    """Search Google Flights and return a dictionary containing flight results.

    Example use from another Python script:
        from datetime import date
        from google_flights_scraper import search_flights
        flights = search_flights("MSY", "MCO", date(2026, 11, 16), adults=2, limit=5)

    The function RETURNS data; it does not ask for input or save a file.
    """
    # Avoid invalid passenger counts and unreasonable output sizes.
    if not 1 <= adults <= 9:
        raise ValueError("Passengers must be between 1 and 9.")
    if not 1 <= limit <= 50:
        raise ValueError("Number of results must be between 1 and 50.")

    # Build the flight query. create_query prepares it; it doesn't search yet.
    query = create_query(
        flights=[FlightQuery(date=travel_date.isoformat(), from_airport=origin, to_airport=destination)],
        trip="one-way",  # No return-trip date is requested.
        seat="economy",
        passengers=Passengers(adults=adults),
        language="en",
        currency="USD",
    )

    # THIS is the network-backed retrieval step from the third-party library.
    # Discard itineraries without any flight legs.
    itineraries = [item for item in get_flights(query) if item.flights]

    # Sort cheapest -> most expensive. Missing prices are pushed to the end.
    # Note: this ranks only the flights returned by the library, not necessarily
    # every flight sold by airlines on this route.
    itineraries.sort(key=lambda item: (item.price is None, item.price if item.price is not None else float("inf")))

    # [:limit] keeps only the requested number of results.
    # enumerate(..., start=1) supplies Priority 1, 2, 3, and so on.
    return {
        "Flights": [
            itinerary_to_json(itinerary, rank)
            for rank, itinerary in enumerate(itineraries[:limit], start=1)
        ]
    }


def main() -> None:
    """Interactive command-line interface for people running this file."""
    try:
        print("Google Flights -> JSON\n")

        # input() pauses and waits for the user to type a value.
        # Validate airport codes immediately so errors are easier to understand.
        origin = check_airport(input("Starting airport (e.g., MSY): "))
        destination = check_airport(input("Destination airport (e.g., ORD): "))
        if origin == destination:
            raise ValueError("The starting and destination airports must be different.")

        # The date function checks formatting and prevents past dates.
        travel_date = parse_search_date(input("Travel date (YYYY-MM-DD): "))

        # When someone just presses Enter, 'or "1"' / 'or "5"' supplies defaults.
        # int() converts those strings into integer numbers.
        adults = int(input("Adult passengers [1]: ").strip() or "1")
        limit = int(input("Maximum results [5]: ").strip() or "5")

        # Call the reusable search function to get our Python dictionary.
        result = search_flights(origin, destination, travel_date, adults, limit)

        # Save the dictionary as readable JSON in the current working folder.
        output = Path("flights.json")
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # Also show the results in the command prompt for convenience.
        print("\n" + json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\nSaved {len(result['Flights'])} result(s) to {output.resolve()}")
        if not result["Flights"]:
            print("No flights returned for this search.", file=sys.stderr)

    except (ValueError, LookupError) as exc:
        # Handle expected bad-input or lookup errors gracefully.
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        # Website changes / network problems may cause the scraper to fail.
        print(f"Google Flights could not be read: {exc}", file=sys.stderr)
        print("The site may have changed, blocked the request, or had no parsable results.", file=sys.stderr)
        sys.exit(1)


# Only run the interactive main() if this file is executed directly.
# Importing search_flights from a second Python file does NOT trigger prompts.
if __name__ == "__main__":
    main()
