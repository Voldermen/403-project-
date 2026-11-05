import helpers
import pandas as pd
import json
from collections import defaultdict

def catorgarize_hubs(lat, lon, datasets=None, local_radius_m=60000):
    """Categorizes stations into direct local hubs vs remote/feeder hubs for a location."""
    all_airports = helpers.find_nearest_airports(lat, lon, 5)
    all_trains = helpers.find_nearest_amtrack(lat, lon, 5)
    all_buses = helpers.find_nearest_greyhound(lat, lon, 5)

    local_airports = all_airports[all_airports["distance_m"] <= local_radius_m]
    local_trains = all_trains[all_trains["distance_m"] <= local_radius_m]
    local_buses = all_buses[all_buses["distance_m"] <= local_radius_m]

    remote_airports = all_airports[all_airports["distance_m"] > local_radius_m]
    remote_trains = all_trains[all_trains["distance_m"] > local_radius_m]
    remote_buses = all_buses[all_buses["distance_m"] > local_radius_m]

    feeder_edges = []

    local_ground = []
    if not local_trains.empty:
        for _, row in local_trains.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            local_ground.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})
    if not local_buses.empty:
        for _, row in local_buses.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            local_ground.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "greyhound"})

    remote_hubs = []
    if not remote_airports.empty:
        for _, row in remote_airports.iterrows():
            airport_id = row.get("iata_code", row.get("name"))
            remote_hubs.append({"name": airport_id, "lat": row["latitude_deg"], "lon": row["longitude_deg"], "mode": "airport"})
    if not remote_trains.empty:
        for _, row in remote_trains.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            remote_hubs.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})
    if not remote_buses.empty:
        for _, row in remote_buses.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            remote_hubs.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "greyhound"})
   
    # Connect local ground stations to remote hubs (Origin Feeder logic)
    for ground in local_ground:
        for hub in remote_hubs:
            dist = helpers.find_distance(ground["lat"], ground["lon"], hub["lat"], hub["lon"])
            
            destination_name = hub["name"]
            destination_type = hub["mode"]
            next_hop_target = hub["name"]
            next_hop_type = hub["mode"]
            
            # If taking a ground mode (greyhound or amtrak) to a non-matching remote hub (e.g., an airport),
            # find the nearest station of that same mode local to the remote hub's location.
            if ground["mode"] == "greyhound" and hub["mode"] != "greyhound":
                hub_buses = helpers.find_nearest_greyhound(hub["lat"], hub["lon"], 5)
                if not hub_buses.empty:
                    nearest_bus_row = hub_buses.iloc[0]
                    destination_name = nearest_bus_row.get("stop_id", nearest_bus_row.get("station_id", nearest_bus_row.get("id", nearest_bus_row.get("stop_name", nearest_bus_row.get("name")))))
                    destination_type = "bus_station"
                    next_hop_target = hub["name"]
                    next_hop_type = hub["mode"]
                else:
                    destination_type = "bus_station"

            elif ground["mode"] == "amtrak" and hub["mode"] != "amtrak":
                hub_trains = helpers.find_nearest_amtrack(hub["lat"], hub["lon"], 5)
                if not hub_trains.empty:
                    nearest_train_row = hub_trains.iloc[0]
                    destination_name = nearest_train_row.get("stop_id", nearest_train_row.get("station_id", nearest_train_row.get("id", nearest_train_row.get("stop_name", nearest_train_row.get("name")))))
                    destination_type = "amtrak"
                    next_hop_target = hub["name"]
                    next_hop_type = hub["mode"]
                else:
                    destination_type = "amtrak"

            feeder_edges.append({
                "local_station": ground["name"],
                "local_mode": ground["mode"],
                "destination_stop": destination_name,
                "destination_type": destination_type,
                "next_hop": next_hop_target,
                "next_hop_type": next_hop_type,
                "transfer_distance_m": dist
            })

    return {
        "has_local_airport": not local_airports.empty,
        "has_local_amtrak": not local_trains.empty,
        "has_local_greyhound": not local_buses.empty,
        "local_hubs": {"airports": local_airports, "amtrak": local_trains, "greyhound": local_buses},
        "remote_hubs": {"airports": remote_airports, "amtrak": remote_trains, "greyhound": remote_buses},
        "feeder_edges": feeder_edges
    }


def categorize_destination_hubs(lat, lon, local_radius_m=60000):
    """Destination feeder logic: exact reverse mirror of the origin feeder."""
    all_airports = helpers.find_nearest_airports(lat, lon, 5)
    all_trains = helpers.find_nearest_amtrack(lat, lon, 5)
    all_buses = helpers.find_nearest_greyhound(lat, lon, 5)

    # 1. Local hubs within local city range at the destination
    local_airports = all_airports[all_airports["distance_m"] <= local_radius_m]
    local_trains = all_trains[all_trains["distance_m"] <= local_radius_m]
    local_buses = all_buses[all_buses["distance_m"] <= local_radius_m]

    # 2. Remote hubs outside city range
    remote_airports = all_airports[all_airports["distance_m"] > local_radius_m]
    remote_trains = all_trains[all_trains["distance_m"] > local_radius_m]
    remote_buses = all_buses[all_buses["distance_m"] > local_radius_m]

    destination_feeder_edges = []

    # Gather local destination ground stations
    local_ground = []
    if not local_trains.empty:
        for _, row in local_trains.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            local_ground.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})
    if not local_buses.empty:
        for _, row in local_buses.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            local_ground.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "greyhound"})

    # Gather remote long-haul hubs
    remote_hubs = []
    if not remote_airports.empty:
        for _, row in remote_airports.iterrows():
            airport_id = row.get("iata_code", row.get("name"))
            remote_hubs.append({"name": airport_id, "lat": row["latitude_deg"], "lon": row["longitude_deg"], "mode": "airport"})
    if not remote_trains.empty:
        for _, row in remote_trains.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            remote_hubs.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "amtrak"})
    if not remote_buses.empty:
        for _, row in remote_buses.iterrows():
            station_id = row.get("stop_id", row.get("station_id", row.get("id", row.get("stop_name", row.get("name")))))
            remote_hubs.append({"name": station_id, "lat": row["stop_lat"], "lon": row["stop_lon"], "mode": "greyhound"})

    # Connect remote hubs TO local destination ground stations (Reverse direction of origin feeder)
    for hub in remote_hubs:
        for ground in local_ground:
            dist = helpers.find_distance(hub["lat"], hub["lon"], ground["lat"], ground["lon"])
            
            origin_name = hub["name"]
            origin_type = hub["mode"]
            next_hop_target = hub["name"]
            next_hop_type = hub["mode"]
            
            # If taking a ground mode (greyhound or amtrak) from a non-matching remote hub (e.g., an airport),
            # find the nearest station of that same mode local to the remote hub's location.
            if ground["mode"] == "greyhound" and hub["mode"] != "greyhound":
                hub_buses = helpers.find_nearest_greyhound(hub["lat"], hub["lon"], 5)
                if not hub_buses.empty:
                    nearest_bus_row = hub_buses.iloc[0]
                    origin_name = nearest_bus_row.get("stop_id", nearest_bus_row.get("station_id", nearest_bus_row.get("id", nearest_bus_row.get("stop_name", nearest_bus_row.get("name")))))
                    origin_type = "bus_station"
                    next_hop_target = hub["name"]
                    next_hop_type = hub["mode"]
                else:
                    origin_type = "bus_station"

            elif ground["mode"] == "amtrak" and hub["mode"] != "amtrak":
                hub_trains = helpers.find_nearest_amtrack(hub["lat"], hub["lon"], 5)
                if not hub_trains.empty:
                    nearest_train_row = hub_trains.iloc[0]
                    origin_name = nearest_train_row.get("stop_id", nearest_train_row.get("station_id", nearest_train_row.get("id", nearest_train_row.get("stop_name", nearest_train_row.get("name")))))
                    origin_type = "amtrak"
                    next_hop_target = hub["name"]
                    next_hop_type = hub["mode"]
                else:
                    origin_type = "amtrak"

            destination_feeder_edges.append({
                "origin_stop": origin_name,
                "origin_type": origin_type,
                "local_destination": ground["name"],
                "local_mode": ground["mode"],
                "next_hop": next_hop_target,
                "next_hop_type": next_hop_type,
                "transfer_distance_m": dist
            })

    return {
        "has_destination_airport": not local_airports.empty,
        "has_destination_amtrak": not local_trains.empty,
        "has_destination_greyhound": not local_buses.empty,
        "destination_feeder_edges": destination_feeder_edges
    }




def get_all_edges(origin_lat, origin_lon, dest_lat, dest_lon):
    origin_airports = helpers.find_nearest_airports(origin_lat, origin_lon, 3)
    origin_trains = helpers.find_nearest_amtrack(origin_lat, origin_lon, 3)
    origin_buses = helpers.find_nearest_greyhound(origin_lat, origin_lon, 1)

    dest_airports = helpers.find_nearest_airports(dest_lat, dest_lon, 3)
    dest_trains = helpers.find_nearest_amtrack(dest_lat, dest_lon, 3)
    dest_buses = helpers.find_nearest_greyhound(dest_lat, dest_lon, 1)

    origin_profile = catorgarize_hubs(origin_lat, origin_lon)
    dest_profile = categorize_destination_hubs(dest_lat, dest_lon) # Use the mirrored function

    airport_name_col = "iata_code" if "iata_code" in origin_airports.columns else "name"
    amtrak_id_col = next((col for col in ["stop_id", "station_id", "id"] if col in origin_trains.columns), "stop_name" if "stop_name" in origin_trains.columns else "name")
    greyhound_id_col = next((col for col in ["stop_id", "station_id", "id"] if col in origin_buses.columns), "stop_name" if "stop_name" in origin_buses.columns else "name")
    
    airport_edges = [{"from": o_row[airport_name_col], "to": d_row[airport_name_col]} for _, o_row in origin_airports.iterrows() for _, d_row in dest_airports.iterrows()]
    amtrak_edges = [{"from": o_row[amtrak_id_col], "to": d_row[amtrak_id_col]} for _, o_row in origin_trains.iterrows() for _, d_row in dest_trains.iterrows()]
    greyhound_edges = [{"from": o_row[greyhound_id_col], "to": d_row[greyhound_id_col]} for _, o_row in origin_buses.iterrows() for _, d_row in dest_buses.iterrows()]

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
    legs = []
    origin_profile = get_edges_output["origin_profile"]
    dest_profile = get_edges_output["dest_profile"]
    query_edges = get_edges_output["query_edges"]
    
    # 1. EXTRACT ORIGIN FEEDER LEGS
    for edge in origin_profile.get("feeder_edges", []):
        legs.append({
            "leg_type": "origin_feeder",
            "mode": edge["local_mode"],
            "origin": {"name": edge["local_station"], "type": edge["local_mode"]},
            "destination": {"name": edge["destination_stop"], "type": edge["destination_type"]},
            "next_hop": edge["next_hop"],
            "next_hop_type": edge["next_hop_type"],
            "transfer_distance_m": edge["transfer_distance_m"]
        })

    # 2. EXTRACT LINE-HAUL LEGS
    for pair in query_edges.get("flight_pairs", []):
        legs.append({
            "leg_type": "line_haul",
            "mode": "flight",
            "origin": {"name": pair["from"], "type": "airport"},
            "destination": {"name": pair["to"], "type": "airport"},
            "next_hop": pair["to"],
            "next_hop_type": "airport"
        })
    # (Amtrak / Greyhound line haul loops remain the same...)


    # 3. EXTRACT DESTINATION FEEDER LEGS
    for edge in dest_profile.get("destination_feeder_edges", []):
        legs.append({
            "leg_type": "destination_feeder",
            "mode": edge["local_mode"],
            "origin": {"name": edge["origin_stop"], "type": edge["origin_type"]},
            "destination": {"name": edge["local_destination"], "type": edge["local_mode"]},
            "next_hop": edge["next_hop"],
            "next_hop_type": edge["next_hop_type"],
            "transfer_distance_m": edge["transfer_distance_m"]
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




def get_paths(origin_lat, origin_lon, dest_lat, dest_lon):
    """main handling function for this file"""

    edges_output = get_all_edges(origin_lat, origin_lon, dest_lat, dest_lon)
    trip_legs = extract_trip_legs(edges_output)

    # Group legs by their mode into a dictionary
    grouped_legs = defaultdict(list)
    for leg in trip_legs:
        mode = leg.get("mode", "unknown")
        grouped_legs[mode].append(leg)

    
    return grouped_legs











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
    # get_paths(
    #     origin_lat=32.5232, origin_lon=-92.6379, 
    #     dest_lat=29.7604, dest_lon=-95.3698
    # )
    # Example test execution (Ruston, LA to katy, TX)
    get_paths(
        origin_lat=32.5232, origin_lon=-92.6379, 
        dest_lat=29.7858, dest_lon=-95.8244
    )
    print("done")

















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