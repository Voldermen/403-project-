import pandas as pd

df = pd.read_csv("raw_greyhound.csv")

df.drop(columns=["stop_desc", "zone_id", "stop_url", "location_type", "parent_station", "wheelchair_boarding", "stop_timezone", "platform_code"], inplace=True)

df.to_csv("cleaned_greyhound.csv", index=False)