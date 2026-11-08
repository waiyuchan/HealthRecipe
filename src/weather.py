"""Opt-in city lookup and real Open-Meteo weather, with honest stale/error states."""

import threading
import time
from datetime import date

import requests

from src.recommendation.recommend import season_on


class WeatherService:
    def __init__(self):
        self.cache = {}
        self.failures = {}
        self.lock = threading.Lock()

    @staticmethod
    def _json(url, params):
        response = requests.get(url, params=params, timeout=(3, 8), allow_redirects=False)
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ValueError("天气响应过大")
        return response.json()

    def search(self, query):
        try:
            data = self._json(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": query, "count": 8, "language": "zh", "format": "json"},
            )
            return [
                {
                    "name": r["name"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "admin1": r.get("admin1", ""),
                    "country": r.get("country", ""),
                    "timezone": r.get("timezone", "auto"),
                }
                for r in data.get("results", [])
            ]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise ValueError("暂时无法搜索城市，请稍后重试；已有城市设置不受影响") from exc

    def current(self, location):
        if location is None:
            return {
                "status": "not_configured",
                "message": "选一个城市，带上真实天气一起选菜",
                "season": season_on(date.today()),
                "source_url": "https://open-meteo.com/",
            }
        key = (location.latitude, location.longitude)
        with self.lock:
            failure = self.failures.get(key)
            if failure and time.time() < failure[0]:
                return failure[1]
            cached = self.cache.get(key)
            age = time.time() - cached[0] if cached else None
            if cached and age < 1800:
                return {**cached[1], "cached": True}
            try:
                data = self._json(
                    "https://api.open-meteo.com/v1/forecast",
                    {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                        "timezone": "auto",
                        "current": "temperature_2m,apparent_temperature,weather_code",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                        "forecast_days": 7,
                    },
                )
                current = data["current"]
                daily = data["daily"]
                forecast = [
                    {
                        "date": d,
                        "min": daily["temperature_2m_min"][i],
                        "max": daily["temperature_2m_max"][i],
                        "description": weather_description(daily["weather_code"][i]),
                    }
                    for i, d in enumerate(daily["time"])
                ]
                result = {
                    "status": "ok",
                    "location": location.model_dump(),
                    "temperature": current["temperature_2m"],
                    "feels_like": current.get("apparent_temperature"),
                    "description": weather_description(current["weather_code"]),
                    "observed_at": current["time"],
                    "timezone": data.get("timezone", ""),
                    "forecast": forecast,
                    "season": season_on(date.fromisoformat(current["time"][:10]), location.latitude),
                    "source_url": "https://open-meteo.com/",
                    "cached": False,
                    "message": "Open-Meteo 天气模型数据，30 分钟缓存",
                }
                self.cache[key] = (time.time(), result)
                return result
            except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
                if cached and age < 21600:
                    fallback = {
                        **cached[1],
                        "status": "stale",
                        "cached": True,
                        "message": "天气更新失败，以下为上次数据，不作为当前气温参与推荐",
                    }
                    self.failures[key] = (time.time() + 60, fallback)
                    return fallback
                fallback = {
                    "status": "unavailable",
                    "location": location.model_dump(),
                    "season": season_on(date.today(), location.latitude),
                    "message": "天气暂时不可用，按季节与饮食记录选菜",
                    "source_url": "https://open-meteo.com/",
                }
                self.failures[key] = (time.time() + 60, fallback)
                return fallback


def weather_description(code):
    if code == 0:
        return "晴"
    if code in {1, 2, 3}:
        return "多云" if code != 3 else "阴"
    if code in {45, 48}:
        return "雾"
    if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
        return "雨"
    if code in {71, 73, 75, 77, 85, 86}:
        return "雪"
    if code in {95, 96, 99}:
        return "雷雨"
    return "天气变化中"
