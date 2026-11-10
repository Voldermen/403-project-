"""
Transportation route planner for continental United States.

Currently built and tested off of examples.json
Assumes clean data

Assumes no time spent walking from station to station
"""



import heapq
import itertools
import json
from datetime import datetime
from pathlib import Path


ALL_ROUTES = Path(__file__).with_name("M_output_unified.json")
def load_methods(json_path=ALL_ROUTES):
    with open(json_path, "r", encoding="utf-8") as file:
        raw_methods = json.load(file)
    return normalize_methods(raw_methods)


def normalize_methods(raw_methods):
    """Convert raw scraper records (any key variant) into the flat dicts
    that build_graph / find_n_lowest_cost_paths expect."""
    methods = []

    for index, item in enumerate(raw_methods):
        # Support both lowercase "method" and capitalized "Method"
        method_obj = item.get("method") or item.get("Method", {})
        
        # Support structures with an "info" wrapper or flat structures
        info = method_obj.get("info", method_obj)

        # Support different variations of start/destination keys (snake_case vs Title Case with spaces)
        start = (
            method_obj.get("starting_location") 
            or method_obj.get("Starting Location")
            or info.get("Starting Location")
        )
        destination = (
            method_obj.get("destination") 
            or method_obj.get("Destination")
            or info.get("Destination")
        )

        if not start or not destination:
            continue

        # A present-but-null Cost would crash float(); skip unpriced records.
        if info.get("Cost") is None:
            continue

        methods.append({
            "id": index,
            "name": (
                info.get("Name")
                or f'{info.get("Type", "Transport")} option {index + 1}'
            ),
            "type": info.get("Type", "Unknown"),
            "priority": int(info.get("Priority", 99)),
            "scope": info.get("Scope", "Unknown"),
            "cost": float(info.get("Cost", 0)),
            "travel_minutes": int(info.get("Travel Time (min)", 0)),
            # None = unscheduled (e.g. walking): can be taken any time.
            "departure": info.get("Departure"),
            "arrival": info.get("Arrival"),
            "date": info.get("Date"),
            "start": start,
            "destination": destination,
        })

    return methods

def debug_methods(json_path=ALL_ROUTES):
    with open(json_path, "r", encoding="utf-8") as file:
        raw_methods = json.load(file)

    total_items = len(raw_methods)
    valid_count = 0
    skipped_count = 0

    for index, item in enumerate(raw_methods):
        method = item.get("method") or item.get("Method", {})
        info = method.get("info", method) or method.get("Info")

        start = (
            method.get("starting_location") 
            or method.get("Starting Location")
            or info.get("Starting Location")
        )
        destination = (
            method.get("destination") 
            or method.get("Destination")
            or info.get("Destination")
        )
        if not start or not destination:
            skipped_count += 1
            print(f"Skipped index {index}: Missing start or destination")
            continue

        valid_count += 1

    print(f"Total in JSON: {total_items}")
    print(f"Valid methods: {valid_count}")
    print(f"Skipped methods: {skipped_count}")
    return valid_count


def count_methods(json_path=ALL_ROUTES):
    with open(json_path, "r", encoding="utf-8") as file:
        raw_methods = json.load(file)

    valid_count = 0

    for item in raw_methods:
        method_obj = item.get("method") or item.get("Method", {})
        info = method_obj.get("info", method_obj)

        start = (
            method_obj.get("starting_location") 
            or method_obj.get("Starting Location")
            or info.get("Starting Location")
        )
        destination = (
            method_obj.get("destination") 
            or method_obj.get("Destination")
            or info.get("Destination")
        )

        if not start or not destination:
            continue

        valid_count += 1

    return valid_count

def time_to_minutes(value):
    """Parse 12-hour, 24-hour, or ISO datetime strings.
    Return total minutes since midnight.
    """
    value = str(value).strip()

    if "T" in value:
        value = value.split("T", 1)[1][:5]

    # Normalize AM/PM and whitespace
    value = value.upper()
    value = " ".join(value.split())

    formats = [
        "%H:%M",       # 24-hour: 13:08
        "%I:%M %p",    # 12-hour: 1:08 AM
        "%I:%M%p",     # 12-hour: 1:08AM
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt).time()
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            pass

    raise ValueError(f"Invalid time format: {value!r}")

def minutes_to_time(value):
    """Converrst minutes into day back into H:M am/pm format
    Im calling noon 12:00pm and midnight 12:00am"""
    value = int(value) % (24 * 60)  # wrap past-midnight times onto the clock
    H = value // 60
    M = value % 60
    suffix = "pm" if H >= 12 else "am"  # 720 (noon) and later is pm
    H = H % 12 or 12                    # 0 -> 12 am, 13 -> 1 pm
    return f"{H}:{M:02d} {suffix}"

def leg_times(method, ready_at):
    """Return (depart, arrive) in minutes from start-day midnight, or None
    if the leg can't be taken when ready at `ready_at`.

    Unscheduled legs (walking) depart the moment you're ready. Scheduled legs
    whose arrival clock time is before departure arrive the next day.
    """
    if method.get("departure") is None or method.get("arrival") is None:
        return ready_at, ready_at + method.get("travel_minutes", 0)

    depart = time_to_minutes(method["departure"])
    if depart < ready_at:
        return None  # it left before you got there
    # Prefer the scraper's duration: it is computed from full timestamps, so it
    # handles multi-day trips and time-zone changes that clock times can't.
    if method.get("travel_minutes", 0) > 0:
        return depart, depart + method["travel_minutes"]
    arrive = time_to_minutes(method["arrival"])
    if arrive < depart:
        arrive += 24 * 60  # overnight arrival
    return depart, arrive


def get_method_duration(method):
    arrive = time_to_minutes(method.get("arrival"))
    depart = time_to_minutes(method.get("departure"))
    
    return arrive - depart

def get_wait_time(method, previous_method):
    begin_wait = time_to_minutes(previous_method.get("arrival"))
    stop_wait = time_to_minutes(method.get("departure"))
    return stop_wait - begin_wait


def location_key(location):
    """takes a location and returns a tuple of the coords
     to act as a key for graph """
    gps = location.get("GPS")
    lat, lon = gps.get("LAT"), gps.get("LONG")
    return (
        round(float(lat), 5),
        round(float(lon), 5)
    )


def resolve_location(query, locations):
    """Looks for given GPS cords or city and state in locations or name of station"""

    #if query is a (lat, lon) tuple or list
    #and has two vals and both are float or int
    if (
        isinstance(query, (tuple, list))
        and len(query)==2
        and all(isinstance(coord, (int, float)) for coord in query)
    ):
        lat, lon = query
        matches = []
        for key, location in locations.items():
            try:
                location_lat = float(location.get("GPS").get("LAT"))
                location_lon = float(location.get("GPS").get("LONG"))
            except (TypeError, ValueError):
                continue

            if location_lat == lat and location_lon == lon:
                matches.append(location_key(location))

    #if query is a city and state or a station
    elif isinstance(query, str):
        query = query.strip().casefold()
        matches = []

        for key, location in locations.items():
            city = str(location.get("City", "")).casefold()
            state = str(location.get("State", "")).casefold()
            name = str(location.get("Name", "")).casefold()

            city_state = f"{city}, {state}"

            if query in (city_state, name):
                matches.append(location_key(location))


    else:
        raise ValueError(
            "query must be a (latitude, longitude) tuple or a city/state string."
        )

    # Remove duplicate matches while preserving order.
    matches = list(dict.fromkeys(matches))

    if not matches:
        raise ValueError(
            f"Could not find location matching {query!r} in the JSON data."
        )

    return matches[0]


def build_graph(methods):
    """this function builds out every edge in the graph
    ie. {A->B via bus and A->C via plane}
    returns all possible locations or hubs
    and all the connections between them or the graph"""
    graph = {}
    locations = {}
    for method in methods:
        #this gets each unique location
        start_key = location_key(method["start"])
        end_key = location_key(method["destination"])
        locations[start_key] = method["start"]
        locations[end_key] = method["destination"]
        #makes a list of destinations and methods
        graph.setdefault(start_key, []).append((end_key, method))
    return graph, locations

# objective name -> what find_n_lowest_cost_paths minimizes
OBJECTIVES = {
    "cost": "cost",
    "arrival": "arrival",
    "time": "arrival",  # older name for "arrival"
    "duration": "duration",
}


def find_n_lowest_cost_paths(methods, origin, destination, startTime, objective, n=3):
    """
    Return up to `n` routes, best first, as a list of format_result dicts.

    objective:
      "cost"     - lowest total price
      "arrival"  - earliest arrival ("time" is accepted as an alias)
      "duration" - least time commuting: from leaving the door (timed to catch
                   the first scheduled leg) to arriving. Waiting at home before
                   the trip is free; layovers between legs count.
    """
    if n < 1:
        raise ValueError("n must be at least 1.")
    kind = OBJECTIVES.get(objective)
    if kind is None:
        raise ValueError(f"Unknown objective {objective!r}. Use one of: {sorted(OBJECTIVES)}")

    graph, locations = build_graph(methods)
    start_key = resolve_location(origin, locations)
    end_key = resolve_location(destination, locations)
    start_time = time_to_minutes(startTime)

    tie = itertools.count()  # tie-breaker so heapq never compares paths
    # trip_start (duration only): when you leave the door. None until the first
    # scheduled leg is chosen, since leading walks can be shifted later for free;
    # until then cost_so_far is just the minutes spent walking.
    # (cost, ready_at, tie, node, path, visited, trip_start)
    queue = [(0.0, start_time, next(tie), start_key, (), frozenset([start_key]), None)]
    labels = {}
    results = []
    seen_routes = set()

    while queue and len(results) < n:
        cost_so_far, ready_at, _, node, path, visited, trip_start = heapq.heappop(queue)

        if node == end_key:
            route = tuple(m["id"] for _, _, m in path if m["type"] != "Walking")
            if route in seen_routes:
                continue
            seen_routes.add(route)
            results.append(
                format_result(list(path), locations, cost_so_far, start_time, objective)
            )
            continue

        for next_node, method in graph.get(node, []):
            if next_node in visited:
                continue
            times = leg_times(method, ready_at)
            if times is None:
                continue
            depart_time, arrive_time = times
            new_start = trip_start

            if kind == "cost":
                new_cost = cost_so_far + method["cost"]
                label = (new_cost, arrive_time)
            elif kind == "arrival":
                # wait + travel time since the search start time
                new_cost = cost_so_far + (arrive_time - ready_at)
                label = (new_cost, arrive_time)
            else:  # duration
                if trip_start is None and method.get("departure") is not None:
                    # First scheduled leg: leave home just in time to walk here
                    new_start = depart_time - cost_so_far
                if new_start is None:
                    new_cost = cost_so_far + (arrive_time - depart_time)
                    label = (new_cost, arrive_time)
                else:
                    new_cost = arrive_time - new_start
                    # Arriving early isn't automatically better here (it can
                    # mean a longer layover), so compare "left home later AND
                    # arrived earlier" instead of "cheaper AND earlier".
                    label = (-new_start, arrive_time)

            # Prune if n labels already beat this one on both label values.
            # The destination is never pruned, so walking variants of one
            # route can't crowd out a genuinely different route.
            if next_node != end_key:
                node_labels = labels.setdefault((next_node, new_start is None), [])
                dominated_by = sum(
                    1 for a, b in node_labels if a <= label[0] and b <= label[1]
                )
                if dominated_by >= n:
                    continue
                node_labels.append(label)

            leg = ((node, ready_at), (next_node, arrive_time), method)
            heapq.heappush(queue, (
                new_cost, arrive_time, next(tie), next_node,
                path + (leg,), visited | {next_node}, new_start,
            ))

    if not results:
        raise ValueError("No route found between the requested locations.")
    return results




##############################################
def format_result(path, locations, total_cost, start_time, objective):
    results = {
        "path":path,
        "locations":locations,
        "total_cost":total_cost,
        "start_time": start_time,
        "objective": objective,

    }
    return results


###################################
#printing funcs for demonstration

def print_path(path):
    
    for i, (start_point, end_point, details) in enumerate(path, start=1):
        
        print("=" * 65)
        print(f"Leg {i}: {details.get('name', 'Unnamed route')}")
        print("=" * 65)
        print(f"  Type:           {details.get('type')}")
        print(f"  Scope:          {details.get('scope')}")
        print(f"  Priority:       {details.get('priority')}")
        print(f"  Date:           {details.get('date')}")
      
        start = details.get("start", {})
        destination = details.get("destination", {})
        print("  DEPARTURE")
        print(f"    City:         {start.get('City')}")
        print(f"    Location:     {start.get('Name')}")
        print(f"    Time:         {details.get('departure')}")
        print(f"    GPS:          {start_point[0]}")

        print("  ARRIVAL")
        print(f"    City:         {destination.get('City')}")
        print(f"    Location:     {destination.get('Name')}")
        print(f"    Time:         {details.get('arrival')}")
        print(f"    GPS:          {end_point[0]}")

        print("  LEG SUMMARY")
        print(f"    Cost:         ${details.get('cost', 0):.2f}")
        print(f"    Duration:     {details.get('travel_minutes')} minutes")
        print()



def print_result(full_trip):
    path = full_trip.get("path")
    locations = full_trip.get("locations")
    start_time = full_trip.get("start_time")
    objective = full_trip.get("objective")
    total_cost = full_trip.get("total_cost")

    # total_cost is whatever the search minimized: dollars for "cost",
    # minutes for "arrival"/"duration". Always show the real ticket price too.
    total_price = sum(details.get("cost", 0) for _, _, details in path)

    print(f"Objective:    {objective}")
    print(f"Total cost:   ${total_price:.2f}")
    if OBJECTIVES.get(objective) == "arrival":
        print(f"Total time:   {total_cost:.0f} minutes (from {minutes_to_time(start_time)} start until arrival)")
    elif OBJECTIVES.get(objective) == "duration":
        print(f"Total time:   {total_cost:.0f} minutes (door to door)")
    print_path(path)


if __name__ == "__main__":
    methods = load_methods()
    #trip test 1 (looking for price)
    origin_lat=32.5232 
    origin_lon=-92.6379
    dest_lat=29.7858
    dest_lon=-95.8244
    # Look up the endpoints by the names add_walking_connections gives them, so
    # this works with whatever trip main_alg last wrote to M_output_unified.json.
    # (Raw coords only work if they exactly match that run's geocoded origin/dest.)
    main_origin = "Trip Origin"
    main_dest = "Trip Destination"
    #origin = (29.9511, -90.0715)
    #dest = "Chicago Midway International Airport"
    start_time = "12:01 am"
    obj = "duration"
    
    # single best route:
    print_result(find_n_lowest_cost_paths(methods, main_origin, main_dest, start_time, obj, n=1)[0])

    # top n routes:
    # results = find_n_lowest_cost_paths(methods, main_origin, main_dest, start_time, obj, n=3)
    # for rank, result in enumerate(results, start=1):
    #     print(f"\n######## Option {rank} of {len(results)} | total {obj}: {result['total_cost']:.2f} ########")
    #     print_result(result)
    
    
    # #trip test 2 (diff dest looking for time)
    # dest = "MadeUpBusStation" #downtown milwakee
    # obj = "time"
    # print_result(find_n_lowest_cost_paths(methods, origin, dest, start_time, obj, n=1)[0])

"""
add info fucntions like
total cost, total time for opposite of cost
and a better formatiing function"""