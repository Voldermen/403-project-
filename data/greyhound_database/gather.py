import csv
import json
import urllib.request
import zipfile
import io

# Unified North American database tracking Greyhound & FlixBus
FEED_URL = "http://gtfs.gis.flix.tech/gtfs_generic_us.zip"

print("Fetching live GTFS package...")
req = urllib.request.Request(FEED_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    zip_bytes = response.read()

parsed_stops = []

with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
    # Open the core stops directory table inside the GTFS format
    with archive.open('stops.txt') as file_data:
        text_stream = io.TextIOWrapper(file_data, encoding='utf-8')
        reader = csv.DictReader(text_stream)
        
        for row in reader:
            parsed_stops.append({
                "stop_id": row.get("stop_id"),
                "stop_name": row.get("stop_name"),
                "latitude": float(row.get("stop_lat")),
                "longitude": float(row.get("stop_lon")),
                "zone_id": row.get("zone_id", "")
            })

# Save structured array out to a clean JSON document
output_filename = "flix_greyhound_coordinates.json"
with open(output_filename, "w", encoding="utf-8") as out_file:
    json.dump(parsed_stops, out_file, indent=4)

print(f"Extraction complete. Saved {len(parsed_stops)} stop records to {output_filename}.")