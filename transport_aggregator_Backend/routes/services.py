"""Connect the three REAL provider modules and optional comparison logic."""
import logging
from google_flights_scraper import search_flights, check_airport, AIRPORTS
from .algorithms import recommend_routes, sort_by_price
from .amtrak_adapter import search_amtrak
from .greyhound_adapter import search_greyhound

logger = logging.getLogger(__name__)


def _status(name, status, message, count=0):
    return {"name": name, "status": status, "message": message, "count": count}


def _city(value):
    # Case-only normalization; we deliberately avoid guessing whether two
    # different names (or nearby metro areas) are the same journey.
    return (value or "").strip().casefold()


def _same_city_pair(route, origin_city, destination_city):
    method = route.get("Method", {})
    return (_city(method.get("Staring Location", {}).get("City")) == _city(origin_city)
            and _city(method.get("Destination", {}).get("City")) == _city(destination_city))


def aggregate_routes(values):
    """Retrieve requested providers. Only compare matching city-to-city routes."""
    origin = check_airport(values["origin"])
    destination = check_airport(values["destination"])
    if origin == destination:
        raise ValueError("Choose different airports.")
    # Two verified airport-to-city mappings help match bus trips to airports.
    # Do NOT infer all airport metros from similar-sounding names.
    airport_city_aliases = {"DFW": "Dallas", "DAL": "Dallas",
                            "IAH": "Houston", "HOU": "Houston"}
    origin_city = airport_city_aliases.get(origin, AIRPORTS[origin].get("city"))
    destination_city = airport_city_aliases.get(destination, AIRPORTS[destination].get("city"))
    matching, unmatched = [], []
    providers = {}

    jobs = [("flights", "Google Flights", True,
             lambda: search_flights(origin, destination, values["travel_date"], adults=values["adults"]))]
    jobs.append(("trains", "Amtrak timetable", bool(values.get("include_train")),
                 lambda: search_amtrak(values["train_origin"], values["train_destination"],
                                       values["travel_date"], adults=values["adults"])))
    jobs.append(("buses", "Greyhound", bool(values.get("include_bus")),
                 lambda: search_greyhound(values["bus_origin"], values["bus_destination"],
                                          values["travel_date"], adults=values["adults"])))

    for key, name, enabled, search in jobs:
        if not enabled:
            providers[key] = _status(name, "not_requested", "Not selected for this search.")
            continue
        try:
            rows = search()
            if not isinstance(rows, list):
                raise TypeError("Provider returned something other than a list of routes.")
            comparable = [row for row in rows if _same_city_pair(row, origin_city, destination_city)]
            other = [row for row in rows if not _same_city_pair(row, origin_city, destination_city)]
            matching.extend(comparable)
            unmatched.extend(other)
            if other:
                status = "different_route" if not comparable else "partial"
                message = (f"{len(other)} result(s) for different cities were excluded from recommendations. "
                           "Check the station/city IDs entered.")
            elif not rows:
                status, message = "empty", "No results were returned."
            else:
                status, message = "ok", f"Retrieved {len(comparable)} matching result(s)."
            if key == "trains" and comparable:
                message += " GTFS provides schedules only; ticket prices are unavailable."
            if key == "buses" and comparable:
                message += " Bus stop GPS may be missing until verified."
            providers[key] = _status(name, status, message, len(rows))
        except Exception:
            logger.exception("%s retrieval failed", key)
            providers[key] = _status(name, "error", f"{name} search failed or was unavailable; other sources may still work.")

    # Preserve each source's Method JSON; sort priced routes first, then unpriced.
    matching = sort_by_price(matching)
    return {
        "routes": matching,
        "unmatched_routes": sort_by_price(unmatched),
        "recommendations": recommend_routes(matching),
        "providers": providers,
    }


def display_route(row):
    """Translate the shared Method JSON into easy HTML template fields."""
    method = row["Method"]
    start = method.get("Staring Location", {})
    end = method.get("Destination", {})
    minutes = method.get("Travel Time (min)")
    return {
        "mode": method.get("Type", "Travel"),
        "priority": method.get("Priority"),
        "cost": method.get("Cost"),
        "duration": f"{int(minutes)//60}h {int(minutes)%60:02d}m" if isinstance(minutes, (int, float)) else "Unknown",
        "departure": method.get("Departure", "—"),
        "arrival": method.get("Arrival", "—"),
        "date": method.get("Date", "—"),
        "start": start.get("Name", "—"),
        "end": end.get("Name", "—"),
        "start_city": start.get("City", ""),
        "end_city": end.get("City", ""),
    }
