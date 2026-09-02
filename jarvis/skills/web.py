"""Web search, weather and quick lookups."""
from __future__ import annotations

import json
import re
import webbrowser
from html.parser import HTMLParser
from urllib.parse import quote_plus, urlparse

from . import skill


def _get(url: str, timeout: int = 8):
    import requests

    return requests.get(url, timeout=timeout, headers={"User-Agent": "Jarvis/1.0"})


class _DDGResults(HTMLParser):
    """Harvest organic results from DuckDuckGo's HTML endpoint."""

    def __init__(self) -> None:
        super().__init__()
        self.results = []          # [{"title","snippet","link"}]
        self._cur = None
        self._capture = None       # "title" | "snippet"

    def _flush(self) -> None:
        if self._cur is not None and self._cur["title"].strip():
            self.results.append(self._cur)
        self._cur = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if tag == "a" and "result__a" in cls:
            self._flush()  # new result begins — the previous one is complete
            self._cur = {"title": "", "snippet": "", "link": dict(attrs).get("href", "")}
            self._capture = "title"
        elif tag in ("a", "td", "div") and "result__snippet" in cls and self._cur is not None:
            self._capture = "snippet"

    def handle_data(self, data):
        if self._cur is not None and self._capture:
            self._cur[self._capture] += data

    def handle_endtag(self, tag):
        if self._capture == "title" and tag == "a":
            self._capture = None
        elif self._capture == "snippet" and tag in ("a", "td", "div"):
            self._capture = None

    def close(self) -> None:
        super().close()
        self._flush()


def _ddg_results(query: str, limit: int = 5):
    try:
        r = _get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=10)
        if r.status_code != 200:
            return []
        p = _DDGResults()
        p.feed(r.text)
        for res in p.results:
            link = res.get("link", "")
            if "uddg=" in link:  # unwrap DDG redirect
                m = re.search(r"uddg=([^&]+)", link)
                if m:
                    from urllib.parse import unquote

                    res["link"] = unquote(m.group(1))
        return p.results[:limit]
    except Exception:
        return []


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
    # Instant-answer API is empty for most queries — fall back to real results.
    results = _ddg_results(q)
    if results:
        lines = [f"Top results for '{q}':"]
        for res in results:
            host = urlparse(res.get("link", "")).netloc.replace("www.", "")
            snippet = re.sub(r"\s+", " ", res.get("snippet", "")).strip()
            lines.append(f"  • {res['title'].strip()}")
            if snippet:
                lines.append(f"      {snippet[:220]}")
            if host:
                lines.append(f"      ↳ {host} — say \"read {res['link']}\" and I'll pull the page")
        return "\n".join(lines)
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
    "Get current top headlines — world news, a topic ('news about AI'), or LOCAL news: "
    "for 'news in my area/near me/local news' use the user's remembered location as topic.",
    {
        "type": "object",
        "properties": {"topic": {"type": "string", "description": "Optional topic"}},
    },
    triggers=["what's the news", "give me the news", "news about {topic}", "headlines",
              "what is the news", "tell me the news", "latest news", "news today",
              "today\"s news", "any news", "get me the news", "news", "headlines", "today\u2019s news",
              "whats on the news", "what is on the news", "tell me whats on the news",
              "what are the headlines", "read me the news", "check the news",
              "news in my area", "local news", "news near me", "whats happening locally",
              "what's happening in my area", "news in {topic}", "news from {topic}"],
)
def _remembered_city() -> str:
    """'lives in Cathedral City' memory → 'Cathedral City'. '' when unknown."""
    try:
        from .. import state
        import re as _re
        for m in state.list_memories(limit=200):
            hit = _re.search(r"user (?:lives in|is based in)\s+(.+?)\.?$",
                             m.get("text", ""), _re.I)
            if hit:
                return hit.group(1).strip(" .")
    except Exception:
        pass
    return ""


def get_news(topic: str = "") -> str:
    import re
    import xml.etree.ElementTree as ET

    t = (topic or "").strip()
    if t.lower() in {"my area", "local", "near me", "my city", "my town", "around me"} or not t:
        t = _remembered_city() if t.lower() in {"my area", "local", "near me",
                                                "my city", "my town", "around me"} else t
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


class _TextExtractor(HTMLParser):
    """Pull readable text out of a web page (drop scripts/styles/nav clutter)."""

    SKIP = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header", "form", "aside"}

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in self.SKIP:
            self._skip += 1
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr") and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            chunk = data.strip()
            if chunk:
                self.parts.append(chunk + " ")


@skill(
    "read_webpage",
    "Open a web page, extract its readable text and return it (title plus the "
    "first couple thousand characters). Use to summarise articles, read pages, "
    "or answer questions about a URL the user gives you.",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Full URL, e.g. https://example.com/article"}},
        "required": ["url"],
    },
    triggers=[
        "read the page {url}",
        "read {url} for me",
        "summarize the page {url}",
        "what does {url} say",
    ],
)
def read_webpage(url: str) -> str:
    u = (url or "").strip().strip('"\'<>')
    if not u:
        return "Give me a URL to read."
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        r = _get(u, timeout=12)
        if r.status_code != 200:
            return f"That page refused to load (HTTP {r.status_code})."
        html = r.text[:900_000]
        parser = _TextExtractor()
        parser.feed(html)
        text = re.sub(r"\n{2,}", "\n", "".join(parser.parts)).strip()
        if len(text) < 120:
            return (
                f"'{parser.title.strip() or u}' didn't yield readable text — it's likely "
                "script-heavy. Say 'open' the page if you'd rather view it."
            )
        head = f"{parser.title.strip()}\n{u}\n\n" if parser.title.strip() else f"{u}\n\n"
        return head + text[:2500] + ("…\n\n(truncated — ask a specific question and I'll answer from the page)" if len(text) > 2500 else "")
    except Exception as exc:
        return f"I couldn't reach that page ({exc})."
