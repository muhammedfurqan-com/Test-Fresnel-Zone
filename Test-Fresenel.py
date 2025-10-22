import streamlit as st
import requests
import numpy as np
import matplotlib.pyplot as plt
import osmnx as ox
from geopy.distance import geodesic

import osmnx as ox
st.write("OSMNX version:", ox.__version__)


st.title("Link Path Profile with Fresnel Zone & OSM Buildings")

# User input
tx_lat = st.number_input("TX Latitude", value=33.6844)
tx_lon = st.number_input("TX Longitude", value=73.0479)
rx_lat = st.number_input("RX Latitude", value=33.7380)
rx_lon = st.number_input("RX Longitude", value=72.8240)
frequency = st.number_input("Frequency (GHz)", value=5.8)

# Google Elevation API key
api_key = st.text_input("Google Elevation API Key", type="password")

if st.button("Generate Path Profile"):
    # Step 1: Get elevation profile
    num_points = 100
    latitudes = np.linspace(tx_lat, rx_lat, num_points)
    longitudes = np.linspace(tx_lon, rx_lon, num_points)
    locations = "|".join([f"{lat},{lon}" for lat, lon in zip(latitudes, longitudes)])

    url = f"https://maps.googleapis.com/maps/api/elevation/json?path={locations}&samples={num_points}&key={api_key}"
    response = requests.get(url)
    data = response.json()

    if data["status"] == "OK":
        elevations = [r["elevation"] for r in data["results"]]
        distances = [geodesic((tx_lat, tx_lon), (lat, lon)).meters for lat, lon in zip(latitudes, longitudes)]

        # Step 2: Get OSM buildings along path
        north, south = max(tx_lat, rx_lat) + 0.002, min(tx_lat, rx_lat) - 0.002
        east, west = max(tx_lon, rx_lon) + 0.002, min(tx_lon, rx_lon) - 0.002
        buildings = ox.geometries_from_bbox(north, south, east, west, tags={"building": True})

        # Step 3: Fresnel zone calculation
        wavelength = 3e8 / (frequency * 1e9)
        total_dist = distances[-1]
        fresnel_radii = []
        for d in distances:
            r = np.sqrt(wavelength * d * (total_dist - d) / total_dist)
            fresnel_radii.append(r)

        # Step 4: Plot
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(distances, elevations, label="Terrain", color="brown")

        # Plot approximate building elevations (as vertical lines)
        if not buildings.empty:
            for _, b in buildings.iterrows():
                if b.geometry.centroid.is_empty:
                    continue
                b_lat, b_lon = b.geometry.centroid.y, b.geometry.centroid.x
                d = geodesic((tx_lat, tx_lon), (b_lat, b_lon)).meters
                height = float(b.get("height", b.get("building:levels", 3)) or 3) * 3
                elev = requests.get(
                    f"https://maps.googleapis.com/maps/api/elevation/json?locations={b_lat},{b_lon}&key={api_key}"
                ).json()["results"][0]["elevation"]
                ax.vlines(d, elev, elev + height, color="gray", lw=3, alpha=0.6)

        ax.plot(distances, np.array(elevations) + np.array(fresnel_radii), "b--", alpha=0.6, label="Fresnel zone top")
        ax.plot(distances, np.array(elevations) - np.array(fresnel_radii), "b--", alpha=0.6, label="Fresnel zone bottom")

        ax.set_xlabel("Distance (m)")
        ax.set_ylabel("Elevation (m)")
        ax.legend()
        st.pyplot(fig)
    else:
        st.error(f"Elevation API error: {data['status']}")
