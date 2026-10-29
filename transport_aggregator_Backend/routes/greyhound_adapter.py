"""Bridge between teammate's Greyhound JSON structure and the shared Method schema.

The provider accepts city UUIDs, not airport codes or names. GPS is unknown
unless verified coordinates are supplied later. Do not invent coordinates.
"""
from uuid import UUID
from greyhound_search import fetch_response, convert_response

BUS_PRIORITY = 99  # Preserve the teammate's documented loader default.


def search_greyhound(origin_uuid, destination_uuid, travel_date, adults=1):
    # The submitted script hardcodes one adult in its provider request.
    # Do not silently quote one-adult fares for multiple passengers.
    if adults != 1:
        raise ValueError("This Greyhound integration currently supports one adult only.")
    try:
        origin_uuid, destination_uuid = str(UUID(origin_uuid)), str(UUID(destination_uuid))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Greyhound city IDs must be valid UUIDs.") from exc
    data = fetch_response(origin_uuid, destination_uuid, travel_date)
    source_rows = convert_response(data)
    output = []
    for item in source_rows:
        source = item["method"]
        info = source["info"]
        start, end = source["starting_location"], source["destination"]
        # Each location has additional metadata in the teammate's output. The
        # shared JSON schema has ONLY City, Name and GPS.
        def to_location(loc):
            gps = loc.get("GPS", {})
            return {"City": loc.get("City"), "Name": loc.get("Name"),
                    "GPS": {"LAT": gps.get("LAT"), "LONG": gps.get("LONG")}}
        output.append({"Method": {
            "Type": "Bus",
            "Priority": BUS_PRIORITY,
            "Cost": info["Cost"],
            "Travel Time (min)": info["Travel Time (min)"],
            "Departure": info["Departure"],
            "Arrival": info["Arrival"],
            "Date": info["Date"],
            "Staring Location": to_location(start),
            "Destination": to_location(end),
        }})
    # Source sorts by departure. Shared output sorts by price.
    return sorted(output, key=lambda row: row["Method"]["Cost"])[:10]
