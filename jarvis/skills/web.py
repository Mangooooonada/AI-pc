"""Web search, weather and quick lookups."""
from __future__ import annotations

import json
import webbrowser
from urllib.parse import quote_plus

from . import skill


def _get(url: str, timeout: int = 8):
    import requests

    return requests.get(url, timeout=timeout, headers={"User-Agent": "Jarvis/1.0"})


@skill(
    "web_search",
    "Search the web and return a short text answer. Use this for facts you are "
    "unsure about or anything recent.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    },
    triggers=["search the web for {query}", "google {query}", "look up {query}"],
)
def web_search(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "What should I search for?"
    try:
        r = _get(f"https://api.duckduckgo.com/?q={quote_plus(q)}&format=json&no_html=1")
        data = r.json()
        if data.get("AbstractText"):
            src = data.get("AbstractSource") or "the web"
            return f"{data['AbstractText']} (via {src})"
        topics = data.get("RelatedTopics") or []
        bits = [t["Text"] for t in topics if isinstance(t, dict) and t.get("Text")][:3]
        if bits:
            return "Here's what I found:\n" + "\n".join(f"  • {b}" for b in bits)
    except Exception:
        pass
    webbrowser.open(f"https://duckduckgo.com/?q={quote_plus(q)}")
    return f"I couldn't summarise that, so I opened a search for '{q}' in your browser."


@skill(
    "get_weather",
    "Get the current weather and today's forecast for a city.",
    {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
    },
    triggers=["what's the weather in {city}", "weather in {city}", "the weather"],
)
def get_weather(city: str = "") -> str:
    place = (city or "").strip()
    try:
        if not place:
            loc = _get("https://ipinfo.io/json").json()
            place = loc.get("city") or "your area"
            lat, lon = (loc.get("loc") or "0,0").split(",")
        else:
            geo = _get(
                "https://geocoding-api.open-meteo.com/v1/search?count=1&name="
                + quote_plus(place)
            ).json()
            results = geo.get("results") or []
            if not results:
                return f"I couldn't find a place called '{place}'."
            lat, lon = results[0]["latitude"], results[0]["longitude"]
            place = results[0]["name"]
        wx = _get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto&forecast_days=1"
        ).json()
        cur = wx["current"]
        daily = wx["daily"]
        codes = {
            0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
            45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle",
            55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
            71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
            81: "rain showers", 82: "violent rain showers", 95: "thunderstorms",
            96: "thunderstorms with hail", 99: "thunderstorms with hail",
        }
        desc = codes.get(cur.get("weather_code"), "unsettled")
        return (
            f"{place}: {cur['temperature_2m']:.0f}°F and {desc}, feels like "
            f"{cur['apparent_temperature']:.0f}°F, wind {cur['wind_speed_10m']:.0f} mph. "
            f"Today {daily['temperature_2m_min'][0]:.0f}° to "
            f"{daily['temperature_2m_max'][0]:.0f}°, "
            f"{daily['precipitation_probability_max'][0]:.0f}% chance of precipitation."
        )
    except Exception as exc:
        return f"I couldn't reach the weather service ({exc})."


@skill(
    "get_news",
    "Get current top headlines, optionally on a topic.",
    {
        "type": "object",
        "properties": {"topic": {"type": "string", "description": "Optional topic"}},
    },
    triggers=["what's the news", "give me the news", "news about {topic}", "headlines"],
)
def get_news(topic: str = "") -> str:
    import re
    import xml.etree.ElementTree as ET

    t = (topic or "").strip()
    url = (
        f"https://news.google.com/rss/search?q={quote_plus(t)}&hl=en-US&gl=US&ceid=US:en"
        if t
        else "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    )
    try:
        xml = _get(url).text
        root = ET.fromstring(xml)
        items = root.findall(".//item")[:5]
        if not items:
            return "No headlines came back."
        lines = [f"Top headlines{f' on {t}' if t else ''}:"]
        for it in items:
            title = re.sub(r"\s+", " ", (it.findtext("title") or "").strip())
            lines.append(f"  • {title}")
        return "\n".join(lines)
    except Exception as exc:
        return f"I couldn't fetch the news ({exc})."


@skill(
    "wikipedia_summary",
    "Get an encyclopedia summary of a person, place, or concept.",
    {
        "type": "object",
        "properties": {"topic": {"type": "string", "description": "Subject to look up"}},
        "required": ["topic"],
    },
    triggers=["who is {topic}", "what is {topic}", "tell me about {topic}"],
)
def wikipedia_summary(topic: str) -> str:
    t = (topic or "").strip()
    if not t:
        return "Look up what?"
    try:
        r = _get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote_plus(t.replace(" ", "_")))
        if r.status_code == 200:
            data = r.json()
            if data.get("extract"):
                return data["extract"]
        srch = _get(
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srsearch="
            + quote_plus(t)
        ).json()
        hits = srch.get("query", {}).get("search", [])
        if hits:
            return wikipedia_summary(hits[0]["title"]) if hits[0]["title"].lower() != t.lower() else "Nothing found."
    except Exception:
        pass
    return web_search(t)
