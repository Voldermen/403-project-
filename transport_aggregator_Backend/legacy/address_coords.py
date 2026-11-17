import requests
from time import sleep

# Author: Jacob Barnhill
# Date: 10/17/2026

# Implementation:
# from address_coords import get_lat_long
# from address_coords import get_address

# Calling get_lat_long with Street, City, and State
#    lat, long = get_lat_long(street="201 Mayfield Avenue", city="Ruston", state="LA")


# Calling get_lat_long with Street and Zip Code
#    lat, long = get_lat_long(street="201 Mayfield Avenue", zip_code="71272")

# Calling get_address with latitude and longitude
# address = get_address(32.595504793333, -92.609987082356)



# Gets coords from an address. Need street + zip or street + city + state. Returns coords if found, returns None if not.
def get_lat_long(street: str, city: str = None, state: str = None, zip_code: str = None) -> tuple:

    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"



    address_parts = [street.strip()]

    if city:
        address_parts.append(city.strip())
    if state:
        address_parts.append(state.strip())
    if zip_code:
        address_parts.append(str(zip_code).strip())

    combined_address = ", ".join(address_parts)

    params = {
        "address": combined_address,
        "benchmark": "4",  # Standard baseline benchmark
        "format": "json",
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        #print("Got API response")
        matches = response.json().get("result", {}).get("addressMatches", [])
        #print("Got coordinate match")

        if matches:
            coords = matches[0].get("coordinates", {})
            # y = Latitude, x = Longitude
            return coords.get("y"), coords.get("x")

    except requests.exceptions.RequestException:
        print("Error")
        pass

    return None, None


# Gets address from coords. Need lat + long. Returns address if found, returns None if not. Returns available parameters when given coordinates.
def get_address(latitude: float, longitude: float) -> str:

    url = "https://nominatim.openstreetmap.org/reverse"

    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 18,
    }

    headers = {
        "User-Agent": "AddressLookupTest"
    }    

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        address = data.get("address", {})

        street = address.get("road")
        house_number = address.get("house_number")

        # City can have different field names
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("hamlet")
        )

        state = address.get("state")
        zip_code = address.get("postcode")

        # Include only fields that are available
        parts = [
            f"{house_number} {street}",
            city,
            state,
            zip_code,
        ]

        # No complete street address found.
        if not street or not house_number:
            return None

        # sleep to prevent overuse (max 1 request per second)
        sleep(1)
        return ", ".join(part for part in parts if part)
        
        

    except requests.exceptions.RequestException as exc:
        print(f"Geocoding request failed: {exc}")
        return None
    except ValueError as exc:
        print(f"Invalid JSON response: {exc}")
        return None

    except requests.exceptions.RequestException:
        print("Error")
        pass

    return None

# Verifying code. Expect this output:
# 32.595504793333 , -92.609987082356
# 201 Mayfield Road, Louisiana, 71270

# lat, long = get_lat_long(street="201 Mayfield Avenue", city="Ruston", state="LA")
# address = get_address(lat, long)
# print(lat , "," , long)
# print(address)
