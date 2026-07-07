

import requests, json, folium

# Download Chicago community area boundaries (free, from Chicago Data Portal)
geojson_url = "https://data.cityofchicago.org/resource/igwz-8jzy.geojson"
r = requests.get(geojson_url)
with open("data/chicago_community_areas.geojson", "wb") as f:
    f.write(r.content)


# print(geojson_url[0][0])
# # Look for the key that holds the neighborhood name, e.g. "community", "name", etc.

# #print(df["chicago_community_area_name"].unique()[:10])
# # Compare the format — casing and spelling must match


# Aggregate median price by neighborhood
neighborhood_stats = (
    df.groupby("chicago_community_area_name")["sale_price"]
    .median()
    .reset_index()
    .rename(columns={"sale_price": "median_price"})
)

with open("data/chicago_community_areas.geojson") as f:
    geojson_data = json.load(f)

m2 = folium.Map(location=[41.8781, -87.6298], zoom_start=11)

folium.Choropleth(
    geo_data=geojson_data,
    data=neighborhood_stats,
    columns=["chicago_community_area_name", "median_price"],
    key_on="feature.properties.community",  # verify this key against the GeoJSON
    fill_color="YlOrRd",
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name="Median Sale Price ($)",
    nan_fill_color="lightgray"
).add_to(m2)

m2.save("test_map_choropleth.html")
print("Saved: test_map_choropleth.html")