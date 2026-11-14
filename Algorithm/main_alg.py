from datetime import date, datetime, timedelta
from helpers import get_lat_long, get_bus_station_gps, get_train_station_gps, find_distance
from process import get_paths
from aggregator import fetch_greyhound_info, fetch_amtrack_info, fetch_plane_info
from least_cost_path import find_n_lowest_cost_paths, normalize_methods, leg_times
import json
import re
import pandas as pd
import copy




""" THE main algorithm only looks at trips on the given day after the start time"""


def collect_all_info(paths, travel_date, origin_lat, origin_lon, dest_lat, dest_lon):
    greyhound_df = pd.read_csv("../data/greyhound_database/cleaned_greyhound.csv")
    amtrak_df = pd.read_csv("../data/amtrack_database/cleaned_amtrack.csv")

    master_list = []

   # 1. Process Greyhound paths
    if "greyhound" in paths:
        for leg in paths["greyhound"]:
            origin_id = leg["origin"]["name"]
            dest_id = leg["destination"]["name"]
            try:
                gh_data = fetch_greyhound_info(origin_id, dest_id, travel_date)
                
                # Ensure gh_data is treated as a list to iterate over items easily
                items = gh_data if isinstance(gh_data, list) else [gh_data]
                
                for item in items:
                    # Navigate into the nested structure to update GPS coordinates
                    method_info = item.get("method", {})
                    
                    # Update starting location GPS if present
                    start_loc = method_info.get("starting_location")
                    if start_loc and "Station ID" in start_loc:
                        start_id = start_loc["Station ID"]
                        start_loc["GPS"] = get_bus_station_gps(start_id, greyhound_df)
                    
                    # Update destination GPS if present
                    dest_loc = method_info.get("destination")
                    if dest_loc and "Station ID" in dest_loc:
                        dest_id = dest_loc["Station ID"]
                        dest_loc["GPS"] = get_bus_station_gps(dest_id, greyhound_df)

                # Extend master list with the updated items
                if isinstance(gh_data, list):
                    master_list.extend(items)
                else:
                    master_list.append(items[0])
                    
            except Exception as e:
                pass
                #print(f"Error fetching Greyhound info for {origin_id} -> {dest_id}: {e}")
   
    # 2. Process Flight paths
    if "flight" in paths:
        for leg in paths["flight"]:
            origin_iata = leg["origin"]["name"]
            dest_iata = leg["destination"]["name"]
            try:
                flight_data = fetch_plane_info(origin_iata, dest_iata, travel_date)
                if isinstance(flight_data, list):
                    master_list.extend(flight_data)
                else:
                    master_list.append(flight_data)
            except Exception as e:
                pass
                #print(f"Error fetching Flight info for {origin_iata} -> {dest_iata}: {e}")

    # 3. Process Amtrak paths
    if "amtrak" in paths:
        for leg in paths["amtrak"]:
            origin_station = leg["origin"]["name"]
            dest_station = leg["destination"]["name"]
            try:
                amtrak_data = fetch_amtrack_info(origin_station, dest_station, travel_date)
                if not amtrak_data:
                    continue
                
                # Handle dictionary wrappers like {"Rides": [...]} if returned by Amtrak scraper
                rides = amtrak_data.get("Rides", amtrak_data) if isinstance(amtrak_data, dict) else amtrak_data
                items = rides if isinstance(rides, list) else [rides]
                
                for item in items:
                    method_info = item.get("Method", {})
                    
                    # Update starting location City and GPS
                    start_loc = method_info.get("StartingLocation") or method_info.get("Starting Location")
                    if start_loc:
                        station_key = start_loc.get("Name") or start_loc.get("Station ID")
                        if station_key:
                            station_data = get_train_station_gps(station_key, amtrak_df)
                            start_loc["GPS"] = {
                                "LAT": station_data["LAT"],
                                "LONG": station_data["LONG"]
                            }
                            start_loc["City"] = station_data["City"]
                    
                    # Update destination City and GPS
                    dest_loc = method_info.get("Destination")
                    if dest_loc:
                        station_key = dest_loc.get("Name") or dest_loc.get("Station ID")
                        if station_key:
                            station_data = get_train_station_gps(station_key, amtrak_df)
                            dest_loc["GPS"] = {
                                "LAT": station_data["LAT"],
                                "LONG": station_data["LONG"]
                            }
                            dest_loc["City"] = station_data["City"]
                master_list.extend(items)
            except Exception as e:
                pass
                #print(f"Error fetching Amtrak info for {origin_station} -> {dest_station}: {e}")
    

    #add walking stuff
    master_list = add_walking_connections(master_list, 25000, origin_lat, origin_lon, dest_lat, dest_lon)
    # Save the giant JSON output
    with open("M_output_unified.json", "w", encoding="utf-8") as f:
        json.dump(master_list, f, ensure_ascii=False, indent=4)

    return master_list




def add_walking_connections(master_list, max_distance_meters=20000, origin_lat=None, origin_lon=None, dest_lat=None, dest_lon=None):
    
    unique_hubs = {}
    
    # 1. Gather all unique stations/hubs (supporting both lowercase and Title Case keys)
    for item in master_list:
        method_info = item.get("method") or item.get("Method", {})
        
        start_loc = (
            method_info.get("starting_location") or 
            method_info.get("Starting Location") or 
            method_info.get("StartingLocation")
        )
        
        dest_loc = (
            method_info.get("destination") or 
            method_info.get("Destination")
        )
        
        for loc in [start_loc, dest_loc]:
            if loc and "GPS" in loc:
                gps = loc["GPS"]
                lat = gps.get("LAT") if gps.get("LAT") is not None else gps.get("Lat")
                lon = gps.get("LONG") if gps.get("LONG") is not None else (gps.get("Lon") or gps.get("Long"))
                
                if lat is not None and lon is not None:
                    station_id = loc.get("Station ID") or loc.get("Name") or f"{lat},{lon}"
                    if station_id not in unique_hubs:
                        unique_hubs[station_id] = {
                            "City": loc.get("City", ""),
                            "State": loc.get("State", ""),
                            "Name": loc.get("Name", "Unknown Hub"),
                            "Station ID": loc.get("Station ID", loc.get("Name", "")),
                            "GPS": {"LAT": lat, "LONG": lon}
                        }

    # Explicitly inject the custom origin and destination into unique_hubs if provided
    if origin_lat is not None and origin_lon is not None:
        origin_id = f"{origin_lat},{origin_lon}"
        if origin_id not in unique_hubs:
            unique_hubs[origin_id] = {
                "City": "Origin City",
                "State": "",
                "Name": "Trip Origin",
                "Station ID": origin_id,
                "GPS": {"LAT": origin_lat, "LONG": origin_lon}
            }

    if dest_lat is not None and dest_lon is not None:
        dest_id = f"{dest_lat},{dest_lon}"
        if dest_id not in unique_hubs:
            unique_hubs[dest_id] = {
                "City": "Destination City",
                "State": "",
                "Name": "Trip Destination",
                "Station ID": dest_id,
                "GPS": {"LAT": dest_lat, "LONG": dest_lon}
            }

    hub_list = list(unique_hubs.values())
    walking_legs = []

    # 2. Compare every unique hub against every other unique hub
    for i in range(len(hub_list)):
        for j in range(i + 1, len(hub_list)):
            hub_a = hub_list[i]
            hub_b = hub_list[j]
            
            lat1, lon1 = hub_a["GPS"]["LAT"], hub_a["GPS"]["LONG"]
            lat2, lon2 = hub_b["GPS"]["LAT"], hub_b["GPS"]["LONG"]
            
            distance = find_distance(lat1, lon1, lat2, lon2)
            
            if distance <= max_distance_meters:
                walking_speed_mps = 83.3 / 60  # ~1.39 m/s (~5 km/h)
                travel_time_min = max(1, int(distance / walking_speed_mps / 60))
                
                # Create bidirectional walking links
                for origin, dest in [(hub_a, hub_b), (hub_b, hub_a)]:
                    walking_leg = {
                        "method": {
                            "info": {
                                "Type": "Walking",
                                "Name": "Walking Transfer",
                                "Scope": "Local",
                                "Cost": 0.0,
                                "Currency": "USD",
                                "Price Basis": "free",
                                "Travel Time (min)": travel_time_min,
                                "Distance (meters)": round(distance, 2),
                                "Transfers": 0,
                                "Trip ID": f"walking:{origin.get('Station ID')}:{dest.get('Station ID')}"
                            },
                            "starting_location": copy.deepcopy(origin),
                            "destination": copy.deepcopy(dest)
                        }
                    }
                    walking_legs.append(walking_leg)

    # 3. Append the new walking connections to the master list
    master_list.extend(walking_legs)
    return master_list











def parse_address(address):
    """Split a one-line US address into (street, city, state, zip).

    Accepts e.g. "123 Main St, Ruston, LA 71270" or "123 Main St, Ruston, LA, 71270".
    Missing city/state/zip come back as None so get_lat_long can skip them.
    """
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        raise ValueError("Address is empty.")

    street = parts[0]
    city = parts[1] if len(parts) > 1 else None
    state = zip_code = None

    # Remaining text holds state and/or zip: "LA 71270", "LA", or "LA", "71270"
    tail = " ".join(parts[2:]).split()
    for token in tail:
        if re.fullmatch(r"\d{5}(-\d{4})?", token):
            zip_code = token
        elif re.fullmatch(r"[A-Za-z]{2}", token):
            state = token.upper()

    return street, city, state, zip_code


# Exclude keywords -> the key used in get_paths' output
MODE_ALIASES = {
    "plane": "flight",
    "train": "amtrak",
    "bus": "greyhound",
}


def filter_paths(paths, exclude=None):
    """Return a copy of `paths` without the excluded modes.

    `exclude` may be a single keyword or a list of them: "plane", "train", "bus"
    (e.g. "plane" or ["bus", "train"]). Walking can't be excluded:
    it's needed to connect the trip origin/destination to the hubs.
    """
    if not exclude:
        return paths
    if isinstance(exclude, str):
        exclude = [exclude]

    excluded_modes = set()
    for name in exclude:
        mode = MODE_ALIASES.get(str(name).strip().lower())
        if mode is None:
            raise ValueError(
                f"Unknown travel method {name!r}. Use one of: {sorted(MODE_ALIASES)}"
            )
        excluded_modes.add(mode)

    return {mode: legs for mode, legs in paths.items() if mode not in excluded_modes}


def _to_datetime_str(travel_date, minutes):
    """Minutes from travel-day midnight -> 'YYYY-MM-DDTHH:MM' (rolls into later days)."""
    if isinstance(travel_date, str):
        travel_date = date.fromisoformat(travel_date)
    day_start = datetime.combine(travel_date, datetime.min.time())
    return (day_start + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def build_route(result, raw_legs, travel_date):
    """Turn one search result into a JSON-ready route dict with full leg details."""
    path = result["path"]

    # Clock times (minutes from travel-day midnight) for each leg
    times = []
    for (_, ready_at), (_, arrive_time), method in path:
        depart_time, _ = leg_times(method, ready_at)
        times.append([depart_time, arrive_time])

    # Unscheduled legs (walking) are computed as leaving the moment you're ready,
    # which puts the first walk at the search start time (e.g. 12:01 am) and a
    # long wait at the station. Shift leading walks to arrive just in time.
    first_scheduled = next(
        (i for i, (_, _, m) in enumerate(path) if m.get("departure") is not None), None
    )
    if first_scheduled is not None:
        for i in range(first_scheduled - 1, -1, -1):
            duration = times[i][1] - times[i][0]
            times[i][1] = times[i + 1][0]
            times[i][0] = times[i][1] - duration

    legs = []
    for i, ((_, _, method), (depart, arrive)) in enumerate(zip(path, times)):
        legs.append({
            "leg_number": i + 1,
            "type": method["type"],
            "name": method["name"],
            "scope": method["scope"],
            "cost": method["cost"],
            "departure": _to_datetime_str(travel_date, depart),
            "arrival": _to_datetime_str(travel_date, arrive),
            "duration_min": arrive - depart,
            "wait_before_min": 0 if i == 0 else depart - times[i - 1][1],
            "from": method["start"],
            "to": method["destination"],
            # Everything the scraper returned for this leg, untouched
            "source_record": raw_legs[method["id"]],
        })

    trip_start, trip_end = times[0][0], times[-1][1]
    return {
        "total_cost": round(sum(leg["cost"] for leg in legs), 2),
        "currency": "USD",
        "total_time_min": trip_end - trip_start,
        "departure": _to_datetime_str(travel_date, trip_start),
        "arrival": _to_datetime_str(travel_date, trip_end),
        "num_legs": len(legs),
        "modes": [leg["type"] for leg in legs],
        "legs": legs,
    }


def main_alg(add1, add2, date, objective="cost", start_time="12:01 am", exclude=None, num_paths=3):
    """take in starting and ending addr, travel date, and earliest start time.
    `exclude` is one or more travel methods to leave out, e.g. "plane" or ["bus", "train"]
    `num_paths` is how many routes to return, best first.
    `objective` is "cost" (cheapest), "arrival" (earliest arrival; "time" also
    works), or "duration" (least time commuting, door to door).
    `rank` is the order for that objective (1 = best)."""
    travel_date = date
    #get lat and lon of origin and destination
    origin_street, origin_city, origin_state, origin_zip = parse_address(add1)
    dest_street, dest_city, dest_state, dest_zip = parse_address(add2)

    origin_lat, origin_lon = get_lat_long(origin_street, origin_city, origin_state, origin_zip)
    dest_lat, dest_lon = get_lat_long(dest_street, dest_city, dest_state, dest_zip)
    ########################
    #some test coords
    # origin_lat=32.5232 
    # origin_lon=-92.6379
    # dest_lat=29.7858
    # dest_lon=-95.8244

    origin = (origin_lat,origin_lon)
    destination = (dest_lat, dest_lon)

    #get the possible paths
    paths = filter_paths(get_paths(origin_lat, origin_lon, dest_lat, dest_lon), exclude)
    with open("M_output.json", "w", encoding="utf-8") as f:
        json.dump(paths, f, ensure_ascii=False, indent=4)
    
    all_legs = collect_all_info(paths, date,  origin_lat,origin_lon, dest_lat, dest_lon)

    # Raw scraper records must be normalized before graph building
    methods = normalize_methods(all_legs)
    results = find_n_lowest_cost_paths(methods, origin, destination, start_time, objective, num_paths)

    return format_routes(results, all_legs, travel_date, {
        "origin_address": add1,
        "destination_address": add2,
        "origin": {"LAT": origin_lat, "LONG": origin_lon},
        "destination": {"LAT": dest_lat, "LONG": dest_lon},
        "date": str(travel_date),
        "start_time": start_time,
        "objective": objective,
        "excluded": exclude,
        "num_paths_requested": num_paths,
    })


def format_routes(results, raw_legs, travel_date, query, out_path="M_routes.json"):
    """Build the final ranked-routes dict from search results and save it."""
    routes = [build_route(r, raw_legs, travel_date) for r in results]

    # results already come back best-first for the chosen objective
    routes = [{"rank": rank, **route} for rank, route in enumerate(routes, start=1)]
    output = {"query": query, "num_routes": len(routes), "routes": routes}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4, default=str)
    return output



    



if __name__ == "__main__":
    today = date.today()
    tomorrow = today + timedelta(days=1)

    colorado_addr = "1301 Pennsylvania St Denver, CO 80203"

    ruston_addr = "1000 E Georgia Ave Ruston, LA 71272"
    #currently planes lose on time since walk from denver airport to dest is too long
    #and if fly into the other aiports you miss the last bus to denver
    routes = main_alg(ruston_addr, colorado_addr, tomorrow, "time", num_paths=3)
    print("full details in M_routes.json")
    # e.g. skip flights and buses:
    # main_alg(ruston_addr, colorado_addr, tomorrow, "time", exclude=["plane", "bus"])
    # e.g. top 3 routes:

    """
    get_paths(
            origin_lat=32.5232, origin_lon=-92.6379, 
            dest_lat=29.7858, dest_lon=-95.8244
        )
        print("done")
    
    """