"""
Method: Without airports
corridor or window idea

Mehtod: Assuming including Airports

Think of trying to get to some aiport/ amtrac from another city
find a bus/ train station (using greyhound api) in my city that can get me to or 
near that city
 
"""

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


def find_nearest_airports(lat,lon):
    """take in a lat and lon of some locationa and return the three closest aiports
    codes and coords"""



def get_hubs(address1, address2):
    
    #get gps of both

    #rank the travel

    

    pass