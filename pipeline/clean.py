import pandas as pd

# Load fetched datasets
sales = pd.read_csv("data/raw_parcel_sales.csv")
universe = pd.read_csv("data/raw_parcel_universe.csv")

# Zero-pad PINs immediately
sales["pin"] = sales["pin"].astype(str).str.zfill(14)
universe["pin"] = universe["pin"].astype(str).str.zfill(14)

#Drop NA rows
universe_slim = universe[[
    "pin", "lat", "lon", "chicago_community_area_name"
]].dropna(subset=["lat", "lon"])


#Join the datasets
df = sales.merge(universe_slim, on="pin", how="inner")


#Filter out outliers
df["sale_price"] = df["sale_price"].astype(float)
df = df[(df["sale_price"] >= 10_000) & (df["sale_price"] < 15_000_000)]
df["lat"] = df["lat"].astype(float)
df["lon"] = df["lon"].astype(float)

CLASS_ROLLUP = {
    "0": "Exempt",
    "1": "Vacant Land",
    "2": "Residential (1-6 units)",
    "3": "Multi-Family (7+ units)",
    "4": "Not-for-Profit",
    "5": "Commercial",
    "6": "Industrial",
    "7": "Industrial Incentive",
    "8": "Commercial Incentive",
    "9": "Industrial Incentive",
}

# The first character of the class code is the major category
df = df.rename(columns={"class": "property_class"})
df["class_category"] = df["property_class"].astype(str).str[0].map(CLASS_ROLLUP).fillna("Unknown")

## Standardizing dates from the dttm
df["standard_sale_date"] = pd.to_datetime(df['sale_date'])


df.to_csv('data/joined_parcel_data.csv', index='False')


