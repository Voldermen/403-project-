import helpers
import pandas as pd


def catorgarize_hubs(lat, lon, datasets=None, local_radius_m=60000): #60km for a city?
    """Categorizes stations into direct local hubs vs remote/feeder hubs for a location."""

    # Fetch top candidate hubs near the point
    all_airports = helpers.find_nearest_airports(lat, lon, 5)
    all_trains = helpers.find_nearest_amtrack(lat, lon, 5)
    all_buses = helpers.find_nearest_greyhound(lat, lon, 5)

    # 1. Direct hubs within local city range
    local_airports = all_airports[all_airports["distance_m"] <= local_radius_m]
    local_trains = all_trains[all_trains["distance_m"] <= local_radius_m]
    local_buses = all_buses[all_buses["distance_m"] <= local_radius_m]
    print("ALL 5 NEAR STOPS")
    print(all_buses)
    print()
    print("LOCAL BUSSES")
    print(local_buses)

    # 2. Hubs outside of city range (candidates for feeder connections)
    remote_airports = all_airports[all_airports["distance_m"] > local_radius_m]
    remote_trains = all_trains[all_trains["distance_m"] > local_radius_m]
    remote_buses = all_buses[all_buses["distance_m"] > local_radius_m]

    # 3. Find feeder transfers (Local Bus/Train -> Remote Airport/Train)
    feeder_edges = []

    # Gather local ground stations
    local_ground = []
    if not local_trains.empty:
        for _, row in local_trains.iterrows():
            name = row.get("stop_name", row.get("name"))
            local_ground.append({"name": name, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})
    if not local_buses.empty:
        for _, row in local_buses.iterrows():
            name = row.get("stop_name", row.get("name"))
            local_ground.append({"name": name, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "greyhound"})

    # Gather remote long-haul hubs
    remote_hubs = []
    if not remote_airports.empty:
        for _, row in remote_airports.iterrows():
            remote_hubs.append({"name": row["name"], "lat": row["latitude_deg"], "lon": row["longitude_deg"], "mode": "airport"})
    if not remote_trains.empty:
        for _, row in remote_trains.iterrows():
            name = row.get("stop_name", row.get("name"))
            remote_hubs.append({"name": name, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})

    # Connect local ground stations to remote hubs
    for ground in local_ground:
        for hub in remote_hubs:
            dist = helpers.find_distance(ground["lat"], ground["lon"], hub["lat"], hub["lon"])
            feeder_edges.append({
                "local_station": ground["name"],
                "local_mode": ground["mode"],
                "remote_hub": hub["name"],
                "remote_mode": hub["mode"],
                "transfer_distance_m": dist
            })

    return {
        "has_local_airport": not local_airports.empty,
        "has_local_amtrak": not local_trains.empty,
        "has_local_greyhound": not local_buses.empty,
        "local_hubs": {
            "airports": local_airports,
            "amtrak": local_trains,
            "greyhound": local_buses
        },
        "remote_hubs": {
            "airports": remote_airports,
            "amtrak": remote_trains,
            "greyhound": remote_buses
        },
        "feeder_edges": feeder_edges
    }


def get_all_edges(origin_lat, origin_lon, dest_lat, dest_lon):
    """
    Gathers origin/destination hub profiles and generates direct mode-to-mode query pairs.
    """
    # 1. Nearby Departure Hubs from Origin
    origin_airports = helpers.find_nearest_airports(origin_lat, origin_lon, 3)
    origin_trains = helpers.find_nearest_amtrack(origin_lat, origin_lon, 3)
    origin_buses = helpers.find_nearest_greyhound(origin_lat, origin_lon, 1)

    # 2. Nearby Arrival Hubs near Destination
    dest_airports = helpers.find_nearest_airports(dest_lat, dest_lon, 3)
    dest_trains = helpers.find_nearest_amtrack(dest_lat, dest_lon, 3)
    dest_buses = helpers.find_nearest_greyhound(dest_lat, dest_lon, 1)

    # 3. Categorize hubs for local vs remote feeder detection
    origin_profile = catorgarize_hubs(origin_lat, origin_lon)
    dest_profile = catorgarize_hubs(dest_lat, dest_lon)

    # 4. Generate direct line-haul query pairs (Edges)
    airport_name_col = "iata_code" if "iata_code" in origin_airports.columns else "name"
    ground_name_col = "stop_name" if "stop_name" in origin_trains.columns else "name"

    airport_edges = [
        {"from": o_row[airport_name_col], "to": d_row[airport_name_col]}
        for _, o_row in origin_airports.iterrows()
        for _, d_row in dest_airports.iterrows()
    ]

    amtrak_edges = [
        {"from": o_row[ground_name_col], "to": d_row[ground_name_col]}
        for _, o_row in origin_trains.iterrows()
        for _, d_row in dest_trains.iterrows()
    ]

    greyhound_edges = [
        {"from": o_row[ground_name_col], "to": d_row[ground_name_col]}
        for _, o_row in origin_buses.iterrows()
        for _, d_row in dest_buses.iterrows()
    ]

    return {
        "origin_profile": origin_profile,
        "dest_profile": dest_profile,
        "query_edges": {
            "flight_pairs": airport_edges,
            "amtrak_pairs": amtrak_edges,
            "greyhound_pairs": greyhound_edges
        }
    }


def extract_trip_legs(get_edges_output):
    """
    Takes the output of get_all_edges and extracts BOTH feeder legs 
    (getting from origin town to regional hubs) and line-haul legs.
    """
    legs = []
    
    origin_profile = get_edges_output["origin_profile"]
    query_edges = get_edges_output["query_edges"]
    
    # -----------------------------------------------------------------
    # 1. EXTRACT FEEDER LEGS (First-mile: Local town -> Remote regional hub)
    # -----------------------------------------------------------------
    for edge in origin_profile.get("feeder_edges", []):
        legs.append({
            "leg_type": "origin_feeder",
            "mode": edge["local_mode"],
            "origin": {"name": edge["local_station"], "type": edge["local_mode"]},
            "destination": {"name": edge["remote_hub"], "type": edge["remote_mode"]},
            "transfer_distance_m": edge["transfer_distance_m"]
        })

    # -----------------------------------------------------------------
    # 2. EXTRACT LINE-HAUL LEGS (Flights, Amtrak, Greyhound pairs)
    # -----------------------------------------------------------------
    # (Optional: slice [:3] here if you want to cap them at 3 options each!)
    for pair in query_edges.get("flight_pairs", [])[:3]:
        legs.append({
            "leg_type": "line_haul",
            "mode": "flight",
            "origin": {"name": pair["from"], "type": "airport"},
            "destination": {"name": pair["to"], "type": "airport"}
        })

    for pair in query_edges.get("amtrak_pairs", [])[:3]:
        legs.append({
            "leg_type": "line_haul",
            "mode": "amtrak",
            "origin": {"name": pair["from"], "type": "train_station"},
            "destination": {"name": pair["to"], "type": "train_station"}
        })

    for pair in query_edges.get("greyhound_pairs", [])[:3]:
        legs.append({
            "leg_type": "line_haul",
            "mode": "greyhound",
            "origin": {"name": pair["from"], "type": "bus_station"},
            "destination": {"name": pair["to"], "type": "bus_station"}
        })

    return legs



def call_transit_api(leg):
    """
    Placeholder function representing your API call for each leg.
    Plug in your requests.get() or SDK client here.
    """
    # Example: response = requests.post("https://api.transit.com/search", json=leg)
    # return response.json()
    
    return {
        "status": "success",
        "queried_mode": leg["mode"],
        "route": f"{leg['origin']['name']} -> {leg['destination']['name']}",
        "mock_api_data": {"price": 120.00, "duration_mins": 90}
    }




##########################################################################################################

def main(origin_lat, origin_lon, dest_lat, dest_lon):
    
    print(f"=== Starting Trip Pipeline ===")
    print(f"Origin Coords: ({origin_lat}, {origin_lon})")
    print(f"Dest Coords:   ({dest_lat}, {dest_lon})\n")
    
   
    edges_output = get_all_edges(origin_lat, origin_lon, dest_lat, dest_lon)
    
    
    trip_legs = extract_trip_legs(edges_output)
    print(f"-> Extracted {len(trip_legs)} total leg(s) to query.\n")
    
    #Loop through each leg, hit the API, and store information
    stored_trip_results = []
    for i, leg in enumerate(trip_legs, 1):
        print(f"[Leg {i}] Mode: {leg['mode'].upper()} ({leg['leg_type']})")
        print(f"         From: {leg['origin']['name']}")
        print(f"         To:   {leg['destination']['name']}")
        
        # Call API function
        api_response = call_transit_api(leg)
        
        # Store information about this leg
        stored_trip_results.append({
            "leg_index": i,
            "leg_info": leg,
            "api_response": api_response
        })
        print(f"         Status: API query stored successfully.\n")
        
    print(f"=== Pipeline Complete. Stored {len(stored_trip_results)} leg responses. ===")
    return stored_trip_results



if __name__ == "__main__":
    # Example test execution (Ruston, LA to Houston, TX)
    main(
        origin_lat=32.5232, origin_lon=-92.6379, 
        dest_lat=29.7604, dest_lon=-95.3698
    )



















def test():
    TEST_COORDINATES = {
        # 1. Major Hub to Major Hub (Tests: direct local access to Airports, Amtrak, and Greyhound on both ends)
        "nyc_to_chicago": {
            "origin": {"name": "NYC (Penn Station area)", "lat": 40.7505, "lon": -73.9934},
            "dest": {"name": "Chicago (Union Station area)", "lat": 41.8786, "lon": -87.6404},
            "expected": "Local airports (JFK/LGA/EWR -> ORD/MDW) and direct Amtrak/Greyhound edges on both ends."
        },

        # 2. Small Town to Major City (Tests: feeder logic, local_airport = False, origin needs ground feeder)
        "ruston_to_houston": {
            "origin": {"name": "Ruston, LA", "lat": 32.5232, "lon": -92.6379},
            "dest": {"name": "Houston, TX", "lat": 29.7604, "lon": -95.3698},
            "expected": "No major local airport in Ruston; should detect feeder connection to Monroe (MLU) or Shreveport (SHV)."
        },

        # 3. College Town / Semi-Remote (Tests: feeder transfers from bus to regional hubs)
        "state_college_to_boston": {
            "origin": {"name": "State College, PA", "lat": 40.7982, "lon": -77.8599},
            "dest": {"name": "Boston, MA", "lat": 42.3519, "lon": -71.0551},
            "expected": "Feeder ground connections from local bus stops to regional airports/train hubs."
        },

        # 4. Regional Transit Corridor (~220 km - Tests: Amtrak/Greyhound dominance)
        "philly_to_dc": {
            "origin": {"name": "Philadelphia, PA", "lat": 39.9526, "lon": -75.1652},
            "dest": {"name": "Washington, DC", "lat": 38.9072, "lon": -77.0369},
            "expected": "Strong Amtrak and Greyhound edges alongside regional flight pairs."
        },

        # 5. Short Distance / Same Metro (<15 km - Tests: Inner-city / local transit check)
        "sf_to_oakland": {
            "origin": {"name": "San Francisco, CA", "lat": 37.7749, "lon": -122.4194},
            "dest": {"name": "Oakland, CA", "lat": 37.8044, "lon": -122.2712},
            "expected": "Distance < 30km rank; short distance local transit check."
        }
    }


    # Run all test cases through your function
    for key, test in TEST_COORDINATES.items():
        print(f"--- Testing: {key} ({test['origin']['name']} -> {test['dest']['name']}) ---")
        
        result = get_all_edges(
            test["origin"]["lat"], test["origin"]["lon"],
            test["dest"]["lat"], test["dest"]["lon"]
        )
        
        print(f"Origin Has Local Airport: {result['origin_profile']['has_local_airport']}")
        print(f"Dest Has Local Airport:   {result['dest_profile']['has_local_airport']}")
        print(f"Flight Edges Found:       {len(result['query_edges']['flight_pairs'])}")
        print(f"Amtrak Edges Found:       {len(result['query_edges']['amtrak_pairs'])}")
        print(f"Greyhound Edges Found:    {len(result['query_edges']['greyhound_pairs'])}")
        print(f"Origin Feeder Edges:      {len(result['origin_profile']['feeder_edges'])}\n")