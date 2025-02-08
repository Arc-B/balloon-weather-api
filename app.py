from flask import Flask, jsonify
import requests
import asyncio
import aiohttp
from collections import defaultdict
import numpy as np
import plotly.graph_objects as go
from dash import Dash, dcc, html

app = Flask(__name__)

# URLs
balloon_url = "https://a.windbornesystems.com/treasure/00.json"
weather_api_key = "8f76930389fb04bf937726393e23f7e2"  
weather_url = "https://api.openweathermap.org/data/2.5/weather"

# Step 1: Fetch Balloon Data
def fetch_balloon_data():
    response = requests.get(balloon_url)
    if response.status_code == 200:
        balloon_data = response.json()
        balloon_data = [entry for entry in balloon_data if len(entry) == 3 and all(np.isfinite(entry))]
        return balloon_data
    return []

# Step 2: Spatial Binning - Reduce API Calls
BIN_SIZE = 0.5  # ~50km bins in lat/lon

def bin_coordinates(balloon_data):
    binned_coords = defaultdict(list)
    for lat, lon, alt in balloon_data:
        if np.isfinite(lat) and np.isfinite(lon):
            bin_lat = round(lat / BIN_SIZE) * BIN_SIZE
            bin_lon = round(lon / BIN_SIZE) * BIN_SIZE
            binned_coords[(bin_lat, bin_lon)].append((lat, lon, alt))
    return binned_coords

# Step 3: Fetch Weather Data Asynchronously
async def fetch_weather(session, lat, lon):
    params = {"lat": lat, "lon": lon, "appid": weather_api_key, "units": "metric"}
    async with session.get(weather_url, params=params) as response:
        if response.status == 200:
            return await response.json()
        return None

async def get_all_weather(binned_coords):
    weather_data = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_weather(session, lat, lon) for (lat, lon) in binned_coords.keys()]
        results = await asyncio.gather(*tasks)

        for (key, result) in zip(binned_coords.keys(), results):
            if result:
                weather_data[key] = {
                    "temperature": result["main"]["temp"],
                    "pressure": result["main"]["pressure"],
                    "wind_speed": result["wind"]["speed"],
                    "weather_desc": result["weather"][0]["description"],
                }
    return weather_data

# Step 4: API Endpoint (Serve JSON Data)
@app.route("/balloon_weather", methods=["GET"])
def balloon_weather():
    balloon_data = fetch_balloon_data()
    if not balloon_data:
        return jsonify({"error": "Failed to fetch balloon data"}), 500
    
    binned_coords = bin_coordinates(balloon_data)
    weather_results = asyncio.run(get_all_weather(binned_coords))
    
    weather_data = []
    for (bin_lat, bin_lon), balloons in binned_coords.items():
        if (bin_lat, bin_lon) in weather_results:
            weather_info = weather_results[(bin_lat, bin_lon)]
            for lat, lon, alt in balloons:
                weather_data.append({
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "temperature": weather_info["temperature"],
                    "pressure": weather_info["pressure"],
                    "wind_speed": weather_info["wind_speed"],
                    "weather_desc": weather_info["weather_desc"]
                })
    
    return jsonify(weather_data)

# Step 5: Serve Interactive Plotly Dashboard
dash_app = Dash(__name__, server=app, url_base_pathname="/dashboard/")

def get_plot():
    weather_data = fetch_balloon_data()
    if not weather_data:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter3d(
        x=[data[1] for data in weather_data],  # Longitude
        y=[data[0] for data in weather_data],  # Latitude
        z=[data[2] for data in weather_data],  # Altitude
        mode='markers',
        marker=dict(
            size=6,
            color=[data[2] for data in weather_data],  # Color by altitude
            colorscale='Jet',
            opacity=0.8
        ),
        name='Balloons'
    ))

    fig.update_layout(
        title="Balloon Positions with Weather Overlay",
        scene=dict(
            xaxis_title='Longitude',
            yaxis_title='Latitude',
            zaxis_title='Altitude'
        )
    )

    return fig

# Define Dash Layout
dash_app.layout = html.Div([
    html.H1("Balloon Weather Visualization"),
    dcc.Graph(figure=get_plot())
])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
