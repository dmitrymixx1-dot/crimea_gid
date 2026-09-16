"""Погода по курортам Крыма через Open-Meteo (без API-ключа).

Параллельный запрос по всем городам, кэш на час (WEATHER_TTL).
Если сеть недоступна — отдаём available=false, фронт скрывает виджет.
"""
import asyncio
import time
from datetime import datetime, timezone

import httpx

from .. import config
from ..config import OPEN_METEO_URL, WEATHER_HTTP_TIMEOUT, WEATHER_TTL

# Курорты: id, название, координаты.
CITIES = [
    ("yalta", "Ялта", 44.4952, 34.1667),
    ("alupka", "Алупка", 44.4508, 34.1258),
    ("gurzuf", "Гурзуф", 44.4486, 34.1239),
    ("sevastopol", "Севастополь", 44.6166, 33.5250),
    ("simferopol", "Симферополь", 44.9528, 34.1024),
    ("bakhchisaray", "Бахчисарай", 44.7697, 33.8639),
    ("koktebel", "Коктебель", 45.0764, 35.1058),
    ("sudak", "Судак", 45.0261, 36.3869),
    ("feodosia", "Феодосия", 45.0294, 36.3697),
    ("kerch", "Керчь", 45.3609, 36.4683),
    ("alushta", "Алушта", 44.7175, 34.4275),
    ("evpatoria", "Евпатория", 45.1904, 34.6472),
    ("saki", "Саки", 45.1261, 33.6014),
]

# WMO weather code → (эмодзи, подпись)
WMO = {
    0: ("☀️", "ясно"), 1: ("🌤️", "в основном ясно"), 2: ("⛅", "переменная облачность"),
    3: ("☁️", "пасмурно"), 45: ("🌫️", "туман"), 48: ("🌫️", "изморозь"),
    51: ("🌦️", "лёгкая морось"), 53: ("🌦️", "морось"), 55: ("🌧️", "сильная морось"),
    56: ("🌧️", "морось"), 57: ("🌧️", "морось"),
    61: ("🌦️", "небольшой дождь"), 63: ("🌧️", "дождь"), 65: ("🌧️", "сильный дождь"),
    66: ("🌧️", "дождь"), 67: ("🌧️", "сильный дождь"),
    71: ("🌨️", "небольшой снег"), 73: ("🌨️", "снег"), 75: ("❄️", "сильный снег"),
    77: ("🌨️", "снежные зёрна"),
    80: ("🌦️", "небольшой ливень"), 81: ("🌧️", "ливень"), 82: ("⛈️", "сильный ливень"),
    85: ("🌨️", "снежные заряды"), 86: ("❄️", "сильный снегопад"),
    95: ("⛈️", "гроза"), 96: ("⛈️", "гроза с градом"), 99: ("⛈️", "сильная гроза"),
}
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _code_info(code) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("🌡️", ""))
    except (TypeError, ValueError):
        return ("🌡️", "")


class WeatherService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}

    async def _fetch_city(self, client: httpx.AsyncClient, city_id: str,
                          name: str, lat: float, lon: float) -> dict:
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto", "forecast_days": 4,
        }
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        cur = data.get("current", {})
        emoji, label = _code_info(cur.get("weather_code"))
        daily = data.get("daily", {})
        forecast = []
        times = daily.get("time", [])
        codes = daily.get("weather_code", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        for i, day in enumerate(times[:4]):
            try:
                # day — это «YYYY-MM-DD» в локальной зоне города; tz-конвертация
                # не нужна (и вредна: naive→UTC сдвигает дату назад в UTC+N).
                dlabel = WEEKDAYS[datetime.fromisoformat(day).weekday()]
            except ValueError:
                dlabel = day[5:]
            femoji, _ = _code_info(codes[i]) if i < len(codes) else ("🌡️", "")
            hi = round(tmax[i]) if i < len(tmax) and tmax[i] is not None else None
            lo = round(tmin[i]) if i < len(tmin) and tmin[i] is not None else None
            forecast.append({"day": dlabel, "emoji": femoji, "max": hi, "min": lo})
        return {
            "id": city_id,
            "name": name,
            "available": True,
            "current": {
                "temp": round(cur.get("temperature_2m", 0)),
                "emoji": emoji,
                "label": label,
                "wind": round(cur.get("wind_speed_10m", 0)),
            },
            "forecast": forecast,
        }

    def _unavailable(self, city_id: str, name: str) -> dict:
        return {"id": city_id, "name": name, "available": False}

    async def get(self, city: str | None = None, refresh: bool = False) -> dict:
        now = time.time()
        wanted = CITIES
        if city:
            wanted = [c for c in CITIES if c[0] == city] or CITIES[:0] or CITIES

        results: dict[str, dict] = {}
        stale: list[tuple] = []
        for c in wanted:
            hit = self._cache.get(c[0])
            if hit and now - hit[0] < WEATHER_TTL and not refresh:
                results[c[0]] = hit[1]
            else:
                stale.append(c)

        if stale:
            async with httpx.AsyncClient(timeout=WEATHER_HTTP_TIMEOUT) as client:
                gathered = await asyncio.gather(
                    *(self._fetch_city(client, c[0], c[1], c[2], c[3]) for c in stale),
                    return_exceptions=True,
                )
            for c, res in zip(stale, gathered):
                if isinstance(res, Exception):
                    results[c[0]] = self._unavailable(c[0], c[1])
                else:
                    self._cache[c[0]] = (now, res)
                    results[c[0]] = res

        cities = [results[c[0]] for c in wanted if c[0] in results]
        online = any(c["available"] for c in cities)
        return {
            "online": online,
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "cities": cities,
        }


weather_service = WeatherService()
