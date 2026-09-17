"""Погода по курортам Крыма через Open-Meteo (без API-ключа).

Параллельный запрос по всем городам, кэш на час (WEATHER_TTL).
Если сеть недоступна — отдаём available=false, фронт скрывает виджет.

Кроме текущего состояния и дневного прогноза сервис отдаёт `hourly` —
температуру, код погоды и вероятность осадков на HOURLY_HOURS вперёд.
Времена в ответе — локальные для города (timezone=auto), поэтому окно
отсчитывается от `current.time` сравнением ISO-строк: конвертация в
пояс устройства тут только испортила бы (naive→UTC сдвигает час назад).
Какое окно показать, решает фронт (`static/hourly.js`) по крымскому
времени — серверный ответ живёт в кэше до часа и «сейчас» в нём стареет.
"""

import asyncio
import time
from datetime import UTC, datetime

import httpx

from ..config import OPEN_METEO_URL, WEATHER_HTTP_TIMEOUT, WEATHER_TTL

# Курорты: id, название, координаты.
CITIES = [
    ("yalta", "Ялта", 44.4994, 34.1553),
    ("alupka", "Алупка", 44.4197, 34.0431),
    ("gurzuf", "Гурзуф", 44.5528, 34.2875),
    ("sevastopol", "Севастополь", 44.6000, 33.5333),
    ("simferopol", "Симферополь", 44.9481, 34.1042),
    ("bakhchisaray", "Бахчисарай", 44.7528, 33.8608),
    ("koktebel", "Коктебель", 44.9597, 35.2403),
    ("sudak", "Судак", 44.8506, 34.9761),
    ("feodosia", "Феодосия", 45.0489, 35.3792),
    ("kerch", "Керчь", 45.3386, 36.4681),
    ("alushta", "Алушта", 44.6672, 34.3978),
    ("evpatoria", "Евпатория", 45.2000, 33.3583),
    ("saki", "Саки", 45.1319, 33.6001),
    ("chernomorskoe", "Черноморское", 45.5031, 32.7050),
    ("shchelkino", "Щёлкино", 45.4236, 35.8186),
    ("belogorsk", "Белогорск", 45.0584, 34.5950),
    ("partenit", "Партенит", 44.5764, 34.3397),
    ("simeiz", "Симеиз", 44.4053, 34.0044),
]

CITY_IDS = frozenset(c[0] for c in CITIES)

# WMO weather code → (эмодзи, подпись)
WMO = {
    0: ("☀️", "ясно"),
    1: ("🌤️", "в основном ясно"),
    2: ("⛅", "переменная облачность"),
    3: ("☁️", "пасмурно"),
    45: ("🌫️", "туман"),
    48: ("🌫️", "изморозь"),
    51: ("🌦️", "лёгкая морось"),
    53: ("🌦️", "морось"),
    55: ("🌧️", "сильная морось"),
    56: ("🌧️", "морось"),
    57: ("🌧️", "морось"),
    61: ("🌦️", "небольшой дождь"),
    63: ("🌧️", "дождь"),
    65: ("🌧️", "сильный дождь"),
    66: ("🌧️", "дождь"),
    67: ("🌧️", "сильный дождь"),
    71: ("🌨️", "небольшой снег"),
    73: ("🌨️", "снег"),
    75: ("❄️", "сильный снег"),
    77: ("🌨️", "снежные зёрна"),
    80: ("🌦️", "небольшой ливень"),
    81: ("🌧️", "ливень"),
    82: ("⛈️", "сильный ливень"),
    85: ("🌨️", "снежные заряды"),
    86: ("❄️", "сильный снегопад"),
    95: ("⛈️", "гроза"),
    96: ("⛈️", "гроза с градом"),
    99: ("⛈️", "сильная гроза"),
}
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Сколько часов вперёд отдаём. Фронт показывает 12 и умеет брать окно
# от фактического часа: ответ живёт в кэше до WEATHER_TTL, а за сутки
# прогноз успевает стать точнее.
HOURLY_HOURS = 24


def _code_info(code) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("🌡️", ""))
    except (TypeError, ValueError):
        return ("🌡️", "")


def _number(value):
    """Число из ответа модели или None: null/мусор не должны ломать прогноз."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value))


def hourly_window(hourly: dict, now_iso, limit: int = HOURLY_HOURS) -> list[dict]:
    """Окно почасового прогноза от текущего часа города.

    `now_iso` — `current.time` из ответа Open-Meteo («2026-09-17T12:15»,
    локальное время города). Сравниваем по часу («2026-09-17T12»)
    лексикографически: ISO-строки упорядочены как время, а конвертация
    в чужой пояс сдвинула бы час. Текущий час попадает в окно — фронт
    подписывает его «сейчас».
    """
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    codes = hourly.get("weather_code") or []
    precips = hourly.get("precipitation_probability") or []
    if not isinstance(times, list) or not times:
        return []

    key = str(now_iso)[:13] if isinstance(now_iso, str) else ""
    start = 0
    if key:
        start = next(
            (i for i, t in enumerate(times) if isinstance(t, str) and t[:13] >= key),
            -1,
        )
        if start == -1:
            # Модель отстала от current (или часы кончились) — не выдумываем
            # окно «сейчас»: отдаём пустой список, фронт прячет блок.
            return []

    out = []
    for i in range(start, min(start + limit, len(times))):
        emoji, _ = _code_info(codes[i] if i < len(codes) else None)
        out.append(
            {
                "t": times[i],
                "temp": _number(temps[i]) if i < len(temps) else None,
                "emoji": emoji,
                "precip": _number(precips[i]) if i < len(precips) else None,
            }
        )
    return out


class WeatherService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}

    async def _fetch_city(
        self, client: httpx.AsyncClient, city_id: str, name: str, lat: float, lon: float
    ) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "hourly": "temperature_2m,weather_code,precipitation_probability",
            "timezone": "auto",
            "forecast_days": 4,
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
            "hourly": hourly_window(data.get("hourly") or {}, cur.get("time")),
        }

    def _unavailable(self, city_id: str, name: str) -> dict:
        return {"id": city_id, "name": name, "available": False}

    async def get(self, city: str | None = None, refresh: bool = False) -> dict:
        now = time.time()
        wanted = CITIES
        if city:
            wanted = [c for c in CITIES if c[0] == city]
            if not wanted:
                raise KeyError(f"город «{city}» не найден")

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
            # gather возвращает ровно по результату на город — strict фиксирует это.
            for c, res in zip(stale, gathered, strict=True):
                if isinstance(res, Exception):
                    results[c[0]] = self._unavailable(c[0], c[1])
                else:
                    self._cache[c[0]] = (now, res)
                    results[c[0]] = res

        cities = [results[c[0]] for c in wanted if c[0] in results]
        online = any(c["available"] for c in cities)
        return {
            "online": online,
            "updated_at": datetime.now(UTC).astimezone().isoformat(),
            "cities": cities,
        }


weather_service = WeatherService()
