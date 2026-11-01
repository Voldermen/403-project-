import csv
import io
import urllib.request
import zipfile

# Unified North American database tracking Greyhound & FlixBus
FEED_URL = "http://gtfs.gis.flix.tech/gtfs_generic_us.zip"

print("Fetching live GTFS package...")
req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as response:
  zip_bytes = response.read()

output_filename = "flix_greyhound_stops.csv"
count = 0

with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
  # Open the core stops directory table inside the GTFS format
  with archive.open("stops.txt") as file_data:
    text_stream = io.TextIOWrapper(file_data, encoding="utf-8")
    reader = csv.DictReader(text_stream)

    # Automatically grab all available column headers from stops.txt
    fieldnames = reader.fieldnames
    print(f"Detected columns: {fieldnames}")
    print(f"Writing all records to {output_filename}...")

    # Open output CSV file and write all rows with every column preserved
    with open(output_filename, "w", encoding="utf-8", newline="") as out_file:
      writer = csv.DictWriter(out_file, fieldnames=fieldnames)
      writer.writeheader()

      for row in reader:
        writer.writerow(row)
        count += 1

print(f"Extraction complete. Saved {count} stop records to {output_filename}.")