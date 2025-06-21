from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import os
import requests
import toml

# --- Configuration Loading Function ---
def load_config():
    """Loads configuration from pyproject.toml."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'pyproject.toml')
    try:
        with open(config_path, 'r') as f:
            config_data = toml.load(f)
            return config_data.get('tool', {}).get('app', {}).get('settings', {})
    except Exception as e:
        print(f"Error loading config in weather_mcp.py: {e}")
        return {}

config = load_config()

API_KEY = config.get('weather_api_key') or "1f30089161907a3c7c4ea5d8a1f3b505"
CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"

if not API_KEY:
    raise ValueError("Weather API key not found. Please set it in config.")

mcp = FastMCP(name="WeatherService")

@mcp.tool()
def get_weather(location: str) -> str:
    """
    Gets the **current weather** for a given location, forgiving user input.
    Tries full query, just city, and suggests similar matches if needed.
    """
    def fetch_weather(query):
        params = {"q": query, "appid": API_KEY, "units": "metric"}
        try:
            response = requests.get(CURRENT_URL, params=params)
            if response.status_code == 200:
                data = response.json()
                city = data.get("name", query.title())
                country = data.get("sys", {}).get("country", "")
                temp = data["main"]["temp"]
                desc = data["weather"][0]["description"]
                humidity = data["main"]["humidity"]
                return (f"Current weather in {city}{', ' + country if country else ''}: "
                        f"{temp}°C, {desc}, humidity {humidity}%.")
            return None
        except Exception:
            return None

    # 1. Try full input
    weather = fetch_weather(location)
    if weather:
        return weather

    # 2. Try just the first word (city)
    city_only = location.split(",")[0].strip()
    if city_only.lower() != location.lower():
        weather = fetch_weather(city_only)
        if weather:
            return weather

    # 3. Try geocoding to suggest matches
    params = {"q": location, "appid": API_KEY, "limit": 3}
    try:
        geocode_resp = requests.get(GEOCODE_URL, params=params)
        if geocode_resp.status_code == 200:
            results = geocode_resp.json()
            if results:
                suggestion_list = [f"{r['name']}, {r.get('country', '')}" for r in results]
                suggestions = "; ".join(suggestion_list)
                return (f"Could not find exact weather for '{location.title()}'. "
                        f"Did you mean: {suggestions}?")
    except Exception:
        pass

    return f"Sorry, I couldn't find any weather info for '{location.title()}'. Please check the city name."

# --- Server Setup ---
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Content-Type", "Accept"]
    )
]

app = mcp.http_app(middleware=middleware, path="/mcp/", stateless_http=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
