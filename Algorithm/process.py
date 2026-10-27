"""
Method: Without airports
corridor or window idea

Mehtod: Assuming including Airports

Think of trying to get to some aiport/ amtrac from another city
find a bus/ train station (using greyhound api) in my city that can get me to or 
near that city
 
"""

import pandas as pd
from math import asin, cos, radians, sin, sqrt


#copied from scripts/transit_route to make use clear
def find_distance(lat1, lon1, lat2, lon2):
    """takes gps of two points, returns the distance in meters"""
    r = 6371000
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))



def rank_distance(lat1, lon1, lat2, lon2):
    """take two points dertmine the rank of travel
        3:interstate/far (will use planes, amtrack)
        2:regional/medium (will use planes, amtrack, and greyhound)
        1:innercity/small (will use the transit_route)
    """
    distance = find_distance(lat1, lon1, lat2, lon2)
    
    #inner city <30km
    if distance <= 30000:
        return 1
    #regional 30-500 km
    elif distance <= 500000:
        return 2
    else:
        return 3




def find_nearest_bus(lat, lon):
    """take in a lat and lon of some location and return the 
    name or coords of the nearest bus station maybe also the distance to it"""
    pass

def find_nearest_amtrack(lat,lon):
    """take in a lat and lon of some location and return the name or coords of
    nearest amteack station and distance to it"""
    try:
        amtrack = pd.read_csv("../data/amtrack_database/cleaned_amtrack.csv")
    except:
        print("Unable to open amtrack dataset")
    # Calculate distance to each airport
    amtrack["distance_m"] = amtrack.apply(
        lambda airport: find_distance(
            lat,
            lon,
            airport["stop_lat"],
            airport["stop_lon"]
        ),
        axis=1
    )        

    # Sort by distance and return the closest three
    return amtrack.sort_values("distance_m").head(5)

    



def find_nearest_airports(lat,lon):
    """take in a lat and lon of some locationa and return the three closest aiports
    codes and coords in a a pandas dataframe"""
    try:
        airports = pd.read_csv("../data/airports_database/cleaned_airport.csv")
    except:
        print("Unable to open airports dataset")

    # Calculate distance to each airport
    airports["distance_m"] = airports.apply(
        lambda airport: find_distance(
            lat,
            lon,
            airport["latitude_deg"],
            airport["longitude_deg"]
        ),
        axis=1
    )

    #only grab important info
    airports = airports[["name","latitude_deg","longitude_deg","icao_code","iata_code","gps_code","local_code","distance_m"]]

    # Sort by distance and return the closest three
    return airports.sort_values("distance_m").head(3)


# Example usage
my_lat = 32.5
my_lon = -92.0

closest_air = find_nearest_airports(
    my_lat,
    my_lon
)
closest_am = find_nearest_amtrack(
    my_lat,
    my_lon
)

print(closest_am)




def get_hubs(address1, address2):
    
    #get gps of both

    #rank the travel

    

    pass