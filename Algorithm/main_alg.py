from datetime import date, timedelta
from helpers import get_lat_long, get_bus_station_gps, get_train_station_gps
from process import get_paths
from aggregator import fetch_greyhound_info, fetch_amtrack_info, fetch_plane_info
import json
import pandas as pd

def collect_all_info(paths, travel_date):
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
                print(f"Error fetching Greyhound info for {origin_id} -> {dest_id}: {e}")
   
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
                print(f"Error fetching Flight info for {origin_iata} -> {dest_iata}: {e}")

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
                print(f"Error fetching Amtrak info for {origin_station} -> {dest_station}: {e}")
    
    
    # Save the giant JSON output
    with open("M_output_unified.json", "w", encoding="utf-8") as f:
        json.dump(master_list, f, ensure_ascii=False, indent=4)

    return master_list


def main_alg(date):
    """take in starting and ending addr and date"""
    #get lat and lon of destinations
    #hardcoded for now Ruston to Katy TX
    origin_lat=32.5232 
    origin_lon=-92.6379
    dest_lat=29.7858
    dest_lon=-95.8244

    #get the possible paths
    paths = get_paths(origin_lat, origin_lon, dest_lat, dest_lon)

    collect_all_info(paths, date)



if __name__ == "__main__":
    today = date.today()
    tomorrow = today + timedelta(days=1)

    main_alg(tomorrow)
    """
    get_paths(
            origin_lat=32.5232, origin_lon=-92.6379, 
            dest_lat=29.7858, dest_lon=-95.8244
        )
        print("done")
    
    """