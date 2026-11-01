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

airports = pd.read_csv("../data/airports_database/cleaned_airport.csv")
greyhound = pd.read_csv("../data/greyhound_database/cleaned_greyhound.csv")
amtrack = pd.read_csv("../data/amtrack_database/cleaned_amtrack.csv")

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




def find_nearest_greyhound(lat, lon, num):
    """take in a lat and lon of some location and return the 
    name or coords of the nearest bus station maybe also the distance to it"""
  
        
    greyhound_df = greyhound.copy()   
    
    # Calculate distance to each airport
    greyhound_df["distance_m"] = greyhound_df.apply(
        lambda greyhound_df: find_distance(
            lat,
            lon,
            greyhound_df["stop_lat"],
            greyhound_df["stop_lon"]
        ),
        axis=1
    )        

    # Sort by distance and return the closest three
    return greyhound_df.sort_values("distance_m").head(num)



    

def find_nearest_amtrack(lat,lon, num):
    """take in a lat and lon of some location and return the name or coords of
    nearest amteack station and distance to it"""
    
    
    amtrack_df = amtrack.copy()
    # Calculate distance to each airport
    amtrack_df["distance_m"] = amtrack_df.apply(
        lambda amtrack_df: find_distance(
            lat,
            lon,
            amtrack_df["stop_lat"],
            amtrack_df["stop_lon"]
        ),
        axis=1
    )        

    # Sort by distance and return the closest three
    return amtrack_df.sort_values("distance_m").head(num)

    



def find_nearest_airports(lat,lon,num):
    """take in a lat and lon of some locationa and return the three closest aiports
    codes and coords in a a pandas dataframe"""
    
    airport_df = airports.copy() 

    # Calculate distance to each airport
    airport_df["distance_m"] = airport_df.apply(
        lambda airport_df: find_distance(
            lat,
            lon,
            airport_df["latitude_deg"],
            airport_df["longitude_deg"]
        ),
        axis=1
    )

    #only grab important info
    airport_df = airport_df[["name","latitude_deg","longitude_deg","icao_code","iata_code","gps_code","local_code","distance_m"]]

    # Sort by distance and return the closest three
    return airport_df.sort_values("distance_m").head(num)




if __name__ == "__main__":

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
    closest_grey = find_nearest_greyhound(
        my_lat,
        my_lon
    )

    print(closest_grey)
