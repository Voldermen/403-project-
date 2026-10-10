import pandas as pd

df = pd.read_csv("raw_airports.csv")

#flights in US
df = df[df["iso_country"] == "US"] 

#regional and international AP
df = df[(df["type"] == "medium_airport") | (df["type"] == "large_airport")]

#Only AP with commercial flights (No military AP)
df = df[df["scheduled_service"] == "yes"]

#output
df.to_csv("cleaned_airport.csv", index=False)