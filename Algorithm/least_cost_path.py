"""
Transportation route planner for continental United States.

Currently built and tested off of examples.json
Assumes clean data

Assumes no time spent walking from station to station
"""



import argparse
import heapq
import json
import math
from datetime import datetime, date, time, timedelta
from pathlib import Path


ALL_ROUTES = Path(__file__).with_name("examples.json")

def load_methods(json_path=ALL_ROUTES):
    with open(json_path, "r", encoding="utf-8") as file:
        raw_methods = json.load(file)

    methods = []

    for index, item in enumerate(raw_methods):
        method = item.get("method", {})
        info = method.get("info", {})
        start = method.get("starting_location")
        destination = method.get("destination")

        if not start or not destination:
            # Skip malformed entries.
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
            "departure": info.get("Departure", "00:00"),
            "arrival": info.get("Arrival", "00:00"),
            "date": info.get("Date"),
            "start": start,
            "destination": destination,
        })

    return methods





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
    suffix = "am"
    value = int(value)
    H = value//60
    M = value%60
    if value>=720: #720 is noon
        suffix = "pm"
    return f"{H}:{M} {suffix}"

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

def reconstruct(previous, end_key):
    """unpacks the path taken and reformats it """
    path = []
    current = end_key
    while current in previous:
        prior_key, method, depart_time, arrive_time = previous[current]

        from_location = prior_key
        to_location = current

        path.append((from_location, to_location, method))
        current = prior_key
    path.reverse()
    return path




def find_lowest_cost_path(methods, origin, destination, startTime, objective):
    """
    Find the route with the lowest sum of listed transportation prices or time spent traveling "fastest".
    This assumes starting point is a some station listed in the methods
    uses lat and lon of each location as the keys

    implements a priorty queue
    and dijkstras alg
    """
    #if want cost or time 
    Time = False
    if objective == "time":
        Time = True

    graph, locations = build_graph(methods)
    start_key = resolve_location(origin, locations)
    end_key = resolve_location(destination, locations)
    start_time  = time_to_minutes(startTime)

    # State includes location and earliest time reached at that location for
    best = {(start_key, start_time): 0.0}#initialze best as start to start with 0 time spent
    queue = [(0.0, start_time, start_key)]
    previous = {}
    best_state_for_location = {start_key: (0.0, start_time)}

    while queue:
        cost_so_far, ready_at, node = heapq.heappop(queue)
        if cost_so_far > best.get((node, ready_at), math.inf):
            continue
        if node == end_key:
            print(f"dest reached with cost {cost_so_far}")
            path = reconstruct(previous, (node, ready_at))
            return format_result(path, locations, cost_so_far, start_time, objective)

        for next_node, method in graph.get(node, []):
            depart_time = time_to_minutes(method.get("departure"))
            arrive_time = time_to_minutes(method.get("arrival"))

            #if looking for fastest we want the duration and layover time
            if Time:
                new_cost = cost_so_far + get_method_duration(method) + get_wait_time(method, previous)
            else:
                new_cost = cost_so_far + method["cost"]
            state = (next_node, arrive_time)


            if new_cost < best.get(state, math.inf):
                best[state] = new_cost
                previous[state] = ((node, ready_at), method, depart_time, arrive_time)
                heapq.heappush(queue, (new_cost, arrive_time, next_node))

    raise ValueError("No route found between the requested locations.")




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

methods = load_methods()
origin = (29.9511, -90.0715)
dest = "Chicago Midway International Airport"
start_time = "12:01 am"
obj = "cost"
print(find_lowest_cost_path(methods, origin, dest, start_time, obj))

"""
add info fucntions like
total cost, total time for opposite of cost
and a better formatiing function"""