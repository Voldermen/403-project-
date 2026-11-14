from address_coords import *


lat, long = get_lat_long(street=input("Input Street Address: "), city=input("Input City: "), state=input("Input State (2 letter): "))
print("Your coords are Lat: " , lat , "Long: ", long)
