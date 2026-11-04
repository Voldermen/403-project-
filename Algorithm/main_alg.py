from datetime import date, timedelta
from helpers import get_lat_long
from process import get_paths
from aggregator import fetch_greyhound_info, fetch_amtrack_info, fetch_plane_info
import json

def collect_all_info(paths, travel_date):
    master_list = []

    # 1. Process Greyhound paths
    if "greyhound" in paths:
        for leg in paths["greyhound"]:
            origin_id = leg["origin"]["name"]
            dest_id = leg["destination"]["name"]
            try:
                gh_data = fetch_greyhound_info(origin_id, dest_id, travel_date)
                # Assuming gh_data returns a list of results or individual items
                if isinstance(gh_data, list):
                    master_list.extend(gh_data)
                else:
                    master_list.append(gh_data)
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
                # Handle dictionary wrappers like {"Rides": [...]} if returned by Amtrak scraper
                rides = amtrak_data.get("Rides", amtrak_data) if isinstance(amtrak_data, dict) else amtrak_data
                if isinstance(rides, list):
                    master_list.extend(rides)
                else:
                    master_list.append(rides)
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