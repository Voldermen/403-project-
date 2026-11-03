
import greyhound.greyhound_search as bus
from datetime import date
import json




def fetch_greyhound_info(origin_id, destination_id):
    today_date = date.today()

    # params = dict(
    #     from_city_id=origin_id, 
    #     to_city_id=destination_id,
    #     departure_date=today_date.strftime('%d.%m.%Y'), # Format required: DD.MM.YYYY
    #     products=json.dumps({'adult': 1}), 
    #     currency='USD', 
    #     locale='en_US',
    #     search_by=search_by, 
    #     include_after_midnight_rides='0',
    #     disable_distribusion_trips='0', 
    #     disable_global_trips='0',
    #     disable_trips=json.dumps(['AU'])
    # )
    data = bus.fetch_response(origin_id, destination_id, today_date)
    print(json.dumps(data))
    final = bus.convert_response(data)
    print(final)

def fetch_amtrack_info():
    pass


def fetch_plane_info():
    pass


tex = "70fe4a43-595a-4723-8b23-1ed1247b62b1"
tech  = "ab615f55-9409-4216-a06f-5cf7769812c5"

fetch_greyhound_info(tech, tex)