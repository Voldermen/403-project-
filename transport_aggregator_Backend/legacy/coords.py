from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError





def get_coordinates(city, state):
    """Outputs coords in decimal degrees,
    example input ("Ruston", "Louisiana")"""

    geolocator = Nominatim(user_agent="city_coordinate_finder")

    location_query = f"{city}, {state}, USA"

    try:
        location = geolocator.geocode(location_query)

        if location:
            lat = location.latitude
            lon = location.longitude

            return lat, lon

        else:
            raise ValueError("Location not found")

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"Geocoding error: {e}")



def get_city_state(lat, lon):
    """it takes in decimal degrees
    Ruston for ex is 32.529722 lat
    -92.640556 lon"""

    geolocator = Nominatim(user_agent="city_coordinate_finder")

    try:
        location = geolocator.reverse(
            (lat, lon),
            exactly_one=True,
            language="en"
        )

        if location:
            address = location.raw.get("address", {})

            city = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or address.get("county")
            )

            state = address.get("state")

            return city, state, address

        else:
            raise ValueError("Location not found")

    except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"Geocoding error: {e}")





