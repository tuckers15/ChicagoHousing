"""
After fetching the parcel sales and parcel universe datasets I wanted a quick pilot of the mapping and joining using the pacel identification number
join. I also ran some quick diagnostics to get an idea of how many rows I'd be dropping due to NA or Null latitude and longitude fields.

Dropped row diagnostics:

=== Universe dropna diagnostic ===
Rows before dropna : 882,739
Rows after dropna  : 882,197
Rows dropped       : 542  (0.1%)

=== Sales inner join diagnostic ===
Sales rows before join : 220,679
Rows after inner join  : 213,942
Sales rows dropped     : 6,737  (3.1%)

Unmatched PIN count    : 6,737
Sample unmatched PINs  : ['17103180800000', '13224360020000', '14323110120000', '17171020430000', '20102100240000']

"""

import pandas as pd
import folium

# Load your two raw fetched datasets
sales = pd.read_csv("data/raw_parcel_sales.csv")
universe = pd.read_csv("data/raw_parcel_universe.csv")

# Zero-pad PINs immediately
sales["pin"] = sales["pin"].astype(str).str.zfill(14)
universe["pin"] = universe["pin"].astype(str).str.zfill(14)

# --- Diagnostic 1: dropna impact on universe ---
universe_before = len(universe)
universe_slim = universe[[
    "pin", "lat", "lon", "chicago_community_area_name"
]].dropna(subset=["lat", "lon"])
universe_after = len(universe_slim)

print("=== Universe dropna diagnostic ===")
print(f"  Rows before dropna : {universe_before:,}")
print(f"  Rows after dropna  : {universe_after:,}")
print(f"  Rows dropped       : {universe_before - universe_after:,}  ({(universe_before - universe_after) / universe_before * 100:.1f}%)")

# # Keep only what you need from universe
# universe_slim = universe[[
#     "pin", "lat", "lon", "chicago_community_area_name"
# ]].dropna(subset=["lat", "lon"])


# --- Diagnostic 2: inner join impact on sales ---
sales_before = len(sales)
df = sales.merge(universe_slim, on="pin", how="inner")
sales_after = len(df)

print("\n=== Sales inner join diagnostic ===")
print(f"  Sales rows before join : {sales_before:,}")
print(f"  Rows after inner join  : {sales_after:,}")
print(f"  Sales rows dropped     : {sales_before - sales_after:,}  ({(sales_before - sales_after) / sales_before * 100:.1f}%)")

# Spot check: a sample of PINs that didn't join
unmatched_pins = sales[~sales["pin"].isin(universe_slim["pin"])]["pin"]
print(f"\n  Unmatched PIN count    : {len(unmatched_pins):,}")
print(f"  Sample unmatched PINs  : {unmatched_pins.sample(min(5, len(unmatched_pins))).tolist()}")


# # Join on PIN
# df = sales.merge(universe_slim, on="pin", how="inner")

# Basic price filter to remove obvious junk
df = df[df["sale_price"].astype(float) >= 10_000]
df["sale_price"] = df["sale_price"].astype(float)
df["lat"] = df["lat"].astype(float)
df["lon"] = df["lon"].astype(float)

# Sample down for performance during testing
sample = df.sample(n=2000, random_state=42)

# --- Test 1: Point marker map ---
m = folium.Map(location=[41.8781, -87.6298], zoom_start=11)

for _, row in sample.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=3,
        color="steelblue",
        fill=True,
        fill_opacity=0.5,
        popup=f"${row['sale_price']:,.0f}"
    ).add_to(m)

m.save("test_map_points.html")
print("Saved: test_map_points.html")
