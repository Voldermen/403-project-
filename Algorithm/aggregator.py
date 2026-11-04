
import greyhound.greyhound_search as bus
import Amtrack_Scraper.Amtrak_Data as train
import flight_scraper.google_flights_scraper as plane
from datetime import date, timedelta
import json


"""Greyhound assumes one rider the rest can change if want to put that in later"""


def fetch_greyhound_info(origin_id, destination_id, date):
    
    data = bus.fetch_response(origin_id, destination_id, date)
   
    return bus.convert_response(data)
    

def fetch_amtrack_info(origin, dest, date):
    
    return train.search_amtrak_gtfs(origin, dest, date)
    

def fetch_plane_info(origin, dest, date):

    return plane.search_flights(origin, dest, date)





#######################################################
#tests
today = date.today()
tomorrow = today + timedelta(days=1)

def test_grey():
    tex = "70fe4a43-595a-4723-8b23-1ed1247b62b1"
    tech  = "ab615f55-9409-4216-a06f-5cf7769812c5"
    fetch_greyhound_info(tech, tex, today)

def test_am():
    New = "NYP"
    wash = "WAS"
    fetch_amtrack_info(New, wash, tomorrow)


def test_flight():
    """use IATA codes"""
    ax = "AEX"
    at = "ATL"
    fetch_plane_info(ax, at, tomorrow)
    

#test_flight()
#test_am()
test_grey()