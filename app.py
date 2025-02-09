from flask import Flask, jsonify
import requests
import asyncio
import aiohttp
import time
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
    print("Balloon API Status Code:", response.status_code)
    
    if response.status_code == 200:
        try:
            balloon_data = response.json()
            #print("Raw Balloon Data (First 5):", balloon_data[:5])  # Print first 5 entries
            
            if isinstance(balloon_data, list) and len(balloon_data) > 0:
                balloon_data = [entry for entry in balloon_data if len(entry) == 3 and all(np.isfinite(entry))]
                print("Filtered Balloon Data (First 5):", balloon_data[:5])  # Debug valid data
                return balloon_data
            else:
                print("Unexpected or Empty Balloon Data")
                return []
        except Exception as e:
            print(f"Error parsing Balloon API JSON: {e}")
            return []
    print("Failed to fetch Balloon Data")
    return []
    
# Step 2: Spatial Binning - Reduce API Calls
BIN_SIZE = 2.0  # Larger bin size reduces API calls

def bin_coordinates(balloon_data):
    binned_coords = defaultdict(list)
    print(f"Processing {len(balloon_data)} balloon entries...")

    for lat, lon, alt in balloon_data:
        if np.isfinite(lat) and np.isfinite(lon):
            bin_lat = round(lat / BIN_SIZE) * BIN_SIZE
            bin_lon = round(lon / BIN_SIZE) * BIN_SIZE
            binned_coords[(bin_lat, bin_lon)].append((lat, lon, alt))

    print(f"Binned {len(binned_coords)} unique locations")
    return binned_coords

# Step 3: Fetch Weather Data Asynchronously with Retry Logic
async def fetch_weather(session, lat, lon):
    params = {"lat": lat, "lon": lon, "appid": weather_api_key, "units": "metric"}
    
    for attempt in range(3):  # Retry up to 3 times
        async with session.get(weather_url, params=params) as response:
            if response.status == 200:
                try:
                    return await response.json()
                except Exception as e:
                    print(f"JSON Parsing Error for ({lat}, {lon}): {e}")
                    return None
            elif response.status == 429:  # Too Many Requests
                print(f"Rate limit hit! Waiting before retrying ({lat}, {lon})...")
                time.sleep(5)  # Only sleep when rate limit is hit
            else:
                print(f" Weather API failed for ({lat}, {lon}) - Status Code: {response.status}")
                return None
    return None

# Step 4: Fetch All Weather Data Efficiently
cached_weather_data = {}  # Cache dictionary

async def get_all_weather(binned_coords):
    global cached_weather_data
    weather_data = {}

    async with aiohttp.ClientSession() as session:
        tasks = []
        for (lat, lon) in binned_coords.keys():
            if (lat, lon) in cached_weather_data:
                weather_data[(lat, lon)] = cached_weather_data[(lat, lon)]
                print(f"Using cached weather data for ({lat}, {lon})")
            else:
                tasks.append(fetch_weather(session, lat, lon))

        results = await asyncio.gather(*tasks)

        for (key, result) in zip(binned_coords.keys(), results):
            if result:
                weather_info = {
                    "temperature": result["main"]["temp"],
                    "pressure": result["main"]["pressure"],
                    "wind_speed": result["wind"]["speed"],
                    "weather_desc": result["weather"][0]["description"],
                }
                weather_data[key] = weather_info
                cached_weather_data[key] = weather_info  # Store in cache

    print(f" Retrieved Weather Data for {len(weather_data)} locations")
    return weather_data

# Step 5: API Endpoint (Serve JSON Data)
@app.route("/balloon_weather", methods=["GET"])
def balloon_weather():
    balloon_data = fetch_balloon_data()
    
    if not balloon_data:
        print(" No balloon data available, returning error")
        return jsonify({"error": "No balloon data available"}), 500

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

    print(f" Final API Response contains {len(weather_data)} entries")
    return jsonify(weather_data)

@app.route("/")
def home():
    return '''
    <h1>Balloon Weather API</h1>
    <p>View JSON data at: <a href="/balloon_weather">/balloon_weather</a></p>
    <p>View 3D Visualization at: <a href="/dashboard/">/dashboard/</a></p>
    '''

# Step 6: Serve Interactive Plotly Dashboard
dash_app = Dash(__name__, server=app, routes_pathname_prefix="/dashboard/")

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
