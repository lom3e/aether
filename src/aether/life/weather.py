"""The weather, from Open-Meteo (free, no key, no account). Only the city name and its coordinates leave the Mac, and every
lookup is written to the privacy ledger. Answers are short and meant to be heard: "A Milano adesso 10 gradi, sereno. Domani
nebbia, tra 8 e 15 gradi."

The user's city is remembered the first time they name one ("che tempo fa a Milano?"), so "che tempo fa?" and the spoken
brief work afterwards.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_CACHE_SECONDS = 1800
_cache: dict[str, tuple[float, Any]] = {}

ASK_RE = re.compile(r"\b(che\s+tempo|meteo|previsioni|piove|piover[àa]|nevica|nevicher[àa]|temperatura|quanti\s+gradi|fa\s+(?:freddo|caldo)|"
                    r"ombrello|weather|forecast|rain(?:ing)?|snow(?:ing)?|temperature|umbrella)\b", re.IGNORECASE)
_CITY_RE = re.compile(r"\b(?:a|ad|in|per|di|at|for)\s+([A-ZÀ-Ý][\wÀ-ÿ'’-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’-]+){0,2})")
_TOMORROW_RE = re.compile(r"\b(domani|tomorrow)\b", re.IGNORECASE)

# WMO weather codes in plain words
_CODES_IT = {0: "sereno", 1: "quasi sereno", 2: "poco nuvoloso", 3: "nuvoloso", 45: "nebbia", 48: "nebbia", 51: "pioviggine", 53: "pioviggine",
             55: "pioviggine", 56: "pioviggine gelata", 57: "pioviggine gelata", 61: "pioggia debole", 63: "pioggia", 65: "pioggia forte",
             66: "pioggia gelata", 67: "pioggia gelata", 71: "neve debole", 73: "neve", 75: "neve forte", 77: "nevischio", 80: "rovesci",
             81: "rovesci", 82: "rovesci forti", 85: "rovesci di neve", 86: "rovesci di neve", 95: "temporale", 96: "temporale con grandine",
             99: "temporale con grandine"}
_CODES_EN = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
             56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
             71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "showers", 81: "showers", 82: "heavy showers",
             85: "snow showers", 86: "snow showers", 95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


class WeatherError(Exception):
    pass


def asks_weather(prompt: str) -> bool:
    return bool(ASK_RE.search(prompt or ""))


def city_in(prompt: str) -> str:
    m = _CITY_RE.search(prompt or "")
    return m.group(1).strip() if m else ""


def _get(url: str, ws: Any, purpose: str) -> dict[str, Any]:
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Aether"}), timeout=4) as r:  # noqa: S310 - fixed https host
            data = json.loads(r.read())
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        data, status = None, "error"
        logger.info("weather lookup failed: %s", type(exc).__name__)
    try:
        from aether.privacy.audit import ledger_for

        ledger = ledger_for(ws) if ws is not None else None
        if ledger is not None:
            ledger.record(provider="open-meteo", model="", local=False, workspace_id=getattr(ws, "id", None), purpose=purpose,
                          messages=1, chars=len(url), status=status, error_kind=None if data else "network")
    except Exception:  # noqa: BLE001
        pass
    if data is None:
        raise WeatherError("network")
    _cache[url] = (time.time(), data)
    return data


def locate(city: str, ws: Any = None, language: str = "it") -> dict[str, Any] | None:
    q = urllib.parse.urlencode({"name": city, "count": 1, "language": "it" if language.startswith("it") else "en"})
    res = (_get(f"{_GEO}?{q}", ws, "weather_place").get("results") or [])
    if not res:
        return None
    r = res[0]
    return {"name": r.get("name") or city, "lat": r["latitude"], "lon": r["longitude"], "tz": r.get("timezone") or "auto"}


def forecast(place: dict[str, Any], ws: Any = None) -> dict[str, Any]:
    q = urllib.parse.urlencode({"latitude": round(place["lat"], 2), "longitude": round(place["lon"], 2),
                                "current": "temperature_2m,weather_code",
                                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                                "timezone": place.get("tz") or "auto", "forecast_days": 2})
    return _get(f"{_FORECAST}?{q}", ws, "weather_forecast")


def describe(place: dict[str, Any], data: dict[str, Any], *, language: str = "it", tomorrow: bool = False, brief: bool = False) -> str:
    en = language.startswith("en")
    words = _CODES_EN if en else _CODES_IT
    d = data.get("daily") or {}
    cur = data.get("current") or {}

    def day(i: int) -> tuple[str, int, int, int]:
        code = (d.get("weather_code") or [None, None])[i]
        return (words.get(code, ""), round((d.get("temperature_2m_min") or [0, 0])[i]), round((d.get("temperature_2m_max") or [0, 0])[i]),
                int((d.get("precipitation_probability_max") or [0, 0])[i] or 0))

    name = place["name"]
    if tomorrow:
        w, lo, hi, rain = day(1)
        umbrella = (" Better take an umbrella." if en else " Meglio portare l'ombrello.") if rain >= 50 else ""
        return (f"Tomorrow in {name}: {w}, between {lo} and {hi} degrees.{umbrella}" if en else
                f"Domani a {name}: {w}, tra {lo} e {hi} gradi.{umbrella}")
    w, lo, hi, rain = day(0)
    now_t = round(cur.get("temperature_2m", 0))
    now_w = words.get(cur.get("weather_code"), w)
    umbrella = ((f" {rain}% chance of rain." if en else f" Pioggia al {rain}%.") if rain >= 40 else "")
    if brief:
        return (f"In {name} it's {now_t} degrees, {now_w}, up to {hi}.{umbrella}" if en else
                f"A {name} ci sono {now_t} gradi, {now_w}, massima {hi}.{umbrella}")
    w1, lo1, hi1, _ = day(1)
    return (f"In {name} it's {now_t} degrees now, {now_w}; today between {lo} and {hi}.{umbrella} Tomorrow {w1}, {lo1} to {hi1}." if en else
            f"A {name} adesso ci sono {now_t} gradi, {now_w}; oggi tra {lo} e {hi}.{umbrella} Domani {w1}, tra {lo1} e {hi1}.")


def answer(ws: Any, store: Any, prompt: str, *, language: str = "it") -> str:
    """The spoken answer to a weather question; remembers the city the first time one is named."""
    en = language.startswith("en")
    city = city_in(prompt)
    saved = (store.settings() or {}).get("home_city", "") if store is not None else ""
    if not city and not saved:
        return "Which city? Tell me, e.g. “weather in Milan”, and I'll remember it." if en else \
            "Per quale città? Dimmelo, per esempio «che tempo fa a Milano», e me la ricordo."
    try:
        place = locate(city or saved, ws, language)
        if not place:
            return f"I can't find “{city}”." if en else f"Non trovo «{city}»."
        if store is not None and city and not saved:
            store.update_settings(home_city=place["name"])
        return describe(place, forecast(place, ws), language=language, tomorrow=bool(_TOMORROW_RE.search(prompt or "")))
    except WeatherError:
        return "I can't reach the weather service right now." if en else "Adesso non riesco a raggiungere il servizio meteo."


def brief_line(ws: Any, store: Any, language: str = "it") -> str:
    """One sentence for the spoken brief, or "" (no city saved, offline): never blocks the brief for long."""
    city = (store.settings() or {}).get("home_city", "") if store is not None else ""
    if not city:
        return ""
    try:
        place = locate(city, ws, language)
        return describe(place, forecast(place, ws), language=language, brief=True) if place else ""
    except WeatherError:
        return ""
