import streamlit as st
import requests
import numpy as np
import matplotlib.pyplot as plt
import overpy
import geopandas as gpd
from shapely.geometry import Polygon
import pandas as pd
from geopy.distance import geodesic

st.set_page_config(page_title="Path Profile & Fresnel Zone", layout="wide")

st.title("📡 Path Profile, Fresnel Zone & LOS Analysis")

st.markdown("""
This tool checks **line-of-sight (LOS)** between two points using:
- **Google Elevation API** for terrain
- **OpenStreetMap (Overpass)** for buildings
- Calculates **Fresnel zone** and detects obstructions
""")

# === User Inputs ===
col1, col2 = st.columns(2)
with col1:
    tx_lat = st.number_input("TX Latitude", value=33.6844, format="%.6f")
    tx_lon = st.number_input("TX Longitude", value=73.0479, format="%.6f")
    tx_height = st.number_input("TX Antenna Height (m)", value=30.0)
with col2:
    rx_lat = st.number_input("RX Latitude", value=33.7380, format="%.6f")
    rx_lon = st.number_input("RX Longitude", value=72.8240, format="%.6f")
    rx_height = st.number_input("RX Antenna Height (m)", value=10.0)

frequency = st.number_input("Frequency (GHz)", value=5.8)
api_key = st.text_input("Google Elevation API Key", type="password")

if st.button("Generate Path Profile"):
    try:
        st.info("Fetching elevation data...")

        # Step 1: Get Elevation Profile
        num_points = 100
        latitudes = np.linspace(tx_lat, rx_lat, num_points)
        longitudes = np.linspace(tx_lon, rx_lon, num_points)
        locations = "|".join([f"{lat},{lon}" for lat, lon in zip(latitudes, longitudes)])
        url = f"https://maps.googleapis.com/maps/api/elevation/json?path={locations}&samples={num_points}&key={api_key}"
        response = requests.get(url)
        data = response.json()

        if data["status"] != "OK":
            st.error(f"Google Elevation API Error: {data.get('error_message', data['status'])}")
            st.stop()

        elevations = [r["elevation"] for r in data["results"]]
        distances = [geodesic((tx_lat, tx_lon), (lat, lon)).meters for lat, lon in zip(latitudes, longitudes)]
        total_dist = distances[-1]

        # Adjust for antenna heights
        los_line = np.linspace(elevations[0] + tx_height, elevations[-1] + rx_height, num_points)

        st.success("Elevation data retrieved successfully!")

        # Step 2: Fetch Buildings from Overpass (OSM)
        st.info("Fetching building data from OpenStreetMap...")
        north, south = max(tx_lat, rx_lat) + 0.002, min(tx_lat, rx_lat) - 0.002
        east, west = max(tx_lon, rx_lon) + 0.002, min(tx_lon, tx_lon) - 0.002

        api = overpy.Overpass()
        query = f"""
        [out:json][timeout:25];
        (
          way["building"]({south},{west},{north},{east});
        );
        out body;
        >;
        out skel qt;
        """
        result = api.query(query)

        building_geoms = []
        for way in result.ways:
            pts = [(float(node.lon), float(node.lat)) for node in way.nodes]
            try:
                building_geoms.append(Polygon(pts))
            except:
                continue

        building_heights = []
        for way in result.ways:
            h = 10.0
            if "height" in way.tags:
                try:
                    h = float(way.tags["height"].replace("m", ""))
                except:
                    pass
            elif "building:levels" in way.tags:
                try:
                    h = float(way.tags["building:levels"]) * 3.0
                except:
                    pass
            building_heights.append(h)

        # Step 3: Fresnel Zone Calculation
        wavelength = 3e8 / (frequency * 1e9)
        fresnel_radii = [np.sqrt(wavelength * d * (total_dist - d) / total_dist) for d in distances]

        # Step 4: Plot
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(distances, elevations, color="brown", label="Terrain")
        ax.plot(distances, los_line, "k-", lw=1, label="LOS line")

        # Plot Fresnel zone
        ax.plot(distances, np.array(los_line) + np.array(fresnel_radii), "b--", alpha=0.6, label="Fresnel zone top")
        ax.plot(distances, np.array(los_line) - np.array(fresnel_radii), "b--", alpha=0.6, label="Fresnel zone bottom")

        # Plot buildings
        if len(building_geoms) > 0:
            for poly, height in zip(building_geoms, building_heights):
                centroid = poly.centroid
                b_lat, b_lon = centroid.y, centroid.x
                d = geodesic((tx_lat, tx_lon), (b_lat, b_lon)).meters
                elev_resp = requests.get(
                    f"https://maps.googleapis.com/maps/api/elevation/json?locations={b_lat},{b_lon}&key={api_key}"
                ).json()
                elev = elev_resp["results"][0]["elevation"]
                ax.vlines(d, elev, elev + height, color="gray", lw=3, alpha=0.5)

        ax.set_xlabel("Distance (m)")
        ax.set_ylabel("Elevation (m)")
        ax.legend()
        ax.set_title("Path Profile with Terrain, Buildings, and Fresnel Zone")
        st.pyplot(fig)

        # Step 5: Obstruction Detection
        obstruction = False
        for i in range(num_points):
            if elevations[i] > (los_line[i] - 0.6 * fresnel_radii[i]):  # 60% Fresnel clearance rule
                obstruction = True
                break

        if obstruction:
            st.error("⚠️ LOS Obstructed! One or more terrain/building points intrude into the Fresnel zone.")
        else:
            st.success("✅ LOS Clear. Fresnel zone is unobstructed.")

    except Exception as e:
        st.error(f"Error: {e}")
