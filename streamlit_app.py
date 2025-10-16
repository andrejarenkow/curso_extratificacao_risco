import folium
import pandas as pd
import geopandas as gpd
from streamlit_folium import st_folium

# Ler arquivo /content/novohamburgo_bairro.shp como geodataframe
gdf = gpd.read_file('/content/novohamburgo_bairro.shp')

# Load the CSV data, specifying the separator
casos_df = pd.read_csv('/content/novohamburgo_casos.csv', sep=';')

# Convert 'bairro' column in casos_df to string type for merging
casos_df['bairro'] = casos_df['bairro'].astype(str)

# Merge the geodataframe and cases dataframe
merged_gdf = gdf.merge(casos_df, left_on='CD_BAIRRO', right_on='bairro')

# Get the centroid of the geodataframe for centering the map
center_lat = merged_gdf.geometry.centroid.y.mean()
center_lon = merged_gdf.geometry.centroid.x.mean()

# Create a base map using Folium, centered on the data
m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

# Define the year for the choropleth and tooltip
year_to_display = '2024' # You can change this to any year column in casos_df

# Add the choropleth layer
folium.Choropleth(
    geo_data=merged_gdf.to_json(),
    data=merged_gdf,
    columns=['CD_BAIRRO', year_to_display],
    key_on='feature.properties.CD_BAIRRO',
    fill_color='YlOrRd',
    fill_opacity=0.7,
    line_opacity=0.2,
    legend_name=f'Casos em {year_to_display}'
).add_to(m)

# Add a GeoJson layer with tooltips for interactivity and remove highlight
folium.GeoJson(
    merged_gdf,
    tooltip=folium.features.GeoJsonTooltip(
        fields=['NM_BAIRRO', year_to_display],
        aliases=['Bairro:', f'Casos em {year_to_display}:'],
        localize=True
    ),
    highlight_function=lambda x: {'weight': 0}, # Remove highlight effect
    style_function=lambda x: {
        'color': 'black',     # Set border color to black
        'weight': 1,          # Set border thickness (adjust as needed)
        'fillOpacity': 0      # Make the fill transparent so choropleth is visible
    }
).add_to(m)


# Add a layer control to toggle layers (optional)
folium.LayerControl().add_to(m)

# Display the map
# call to render Folium map in Streamlit
st_data = st_folium(m, width=725, returned_objects=[])
