import pandas as pd

df = pd.read_csv("raw_amtrack.csv")

#just removing the url pretty much
df = df.drop(columns="stop_url")

#output
df.to_csv("cleaned_amtrack.csv", index=False)