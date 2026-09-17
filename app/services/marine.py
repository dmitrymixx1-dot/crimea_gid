"""Море у берегов Крыма: температура воды и волнение (Open-Meteo Marine).

Купальный индекс считаем **на сервере**: и температура воды, и волна
приходят из модели, а не от устройства, поэтому «комфортно / прохладно /
опасно» — одно и то же на телефоне в Ялте и в Екатеринбурге. Фронт лишь
рисует готовый вердикт.

Точки вынесены на 1–5 км от берега: морская модель считает только по
воде, и координата на суше вернула бы пустой ответ. У Симферополя,
Бахчисарая и Белогорска моря нет — для них точек в списке тоже нет
(согласованность с `CITIES` держат тесты).

Пороги вердикта сравниваются с «сырыми» значениями модели, а не с
округлёнными для показа: 22.6 °C — это ещё не 23 °C. Волна важнее
температуры: безопасность выше удовольствия.
"""

import asyncio
import time
from datetime import UTC, datetime

import httpx

from ..config import MARINE_HTTP_TIMEOUT, MARINE_TTL, MARINE_URL

# Курорты с выходом к морю: id совпадает с id погоды (`weather.CITIES`),
# координаты — открытая вода рядом с городом.
SEA_POINTS = [
    ("yalta", "Ялта", 44.4850, 34.1700),
    ("alupka", "Алупка", 44.4050, 34.0400),
    ("gurzuf", "Гурзуф", 44.5380, 34.3000),
    ("sevastopol", "Севастополь", 44.5850, 33.4500),
    ("alushta", "Алушта", 44.6500, 34.4000),
    ("partenit", "Партенит", 44.5600, 34.3400),
    ("simeiz", "Симеиз", 44.3900, 34.0100),
    ("evpatoria", "Евпатория", 45.1950, 33.3300),
    ("saki", "Саки", 45.1300, 33.5600),
    ("chernomorskoe", "Черноморское", 45.5050, 32.6700),
    ("koktebel", "Коктебель", 44.9450, 35.2400),
    ("sudak", "Судак", 44.8350, 34.9900),
    ("feodosia", "Феодосия", 45.0300, 35.3800),
    ("kerch", "Керчь", 45.3300, 36.4500),
    ("shchelkino", "Щёлкино", 45.4000, 35.8200),
]

SEA_IDS = frozenset(p[0] for p in SEA_POINTS)

# Пороги купального индекса.
WAVE_DANGER = 1.5  # м — волна, при которой купаться опасно
WAVE_ROUGH = 1.0  # м — волна, при которой купаться не стоит
TEMP_COMFORT = 23.0  # °C — «вода как парное молоко»
TEMP_OK = 20.0  # °C — купаться можно
TEMP_COOL = 16.0  # °C — прохладно, для закалённых


def _meters(value: float) -> str:
    """0.3 → «0,3» — запятая как в русской типографике."""
    return f"{value:.1f}".replace(".", ",")


def wave_label(height: float | None) -> str:
    """Словесная подпись волнения — без неё «0,3 м» ничего не говорит."""
    if height is None:
        return ""
    if height < 0.3:
        return "штиль"
    if height < 0.6:
        return "лёгкая рябь"
    if height < WAVE_ROUGH:
        return "небольшая волна"
    if height < WAVE_DANGER:
        return "заметное волнение"
    return "сильное волнение"


def verdict(water_temp: float | None, wave_height: float | None) -> dict:
    """Купальный индекс: (code, emoji, label).

    Порядок проверок — от безопасности к удовольствию: высокая волна
    отменяет купание, даже если вода тёплая. Нет данных о воде — честно
    говорим «нет данных», а не выдумываем вердикт.
    """
    if wave_height is not None and wave_height >= WAVE_DANGER:
        return {
            "code": "danger",
            "emoji": "⛔",
            "label": f"купаться опасно: волна {_meters(wave_height)} м",
        }
    if wave_height is not None and wave_height >= WAVE_ROUGH:
        return {
            "code": "rough",
            "emoji": "⚠️",
            "label": f"купаться не стоит: волна {_meters(wave_height)} м",
        }
    if water_temp is None:
        return {"code": "no_data", "emoji": "🌊", "label": "нет данных о воде"}
    if water_temp >= TEMP_COMFORT:
        return {"code": "comfort", "emoji": "🏊", "label": "купаться комфортно"}
    if water_temp >= TEMP_OK:
        return {"code": "ok", "emoji": "👍", "label": "купаться можно"}
    if water_temp >= TEMP_COOL:
        return {"code": "cool", "emoji": "🧊", "label": "прохладно — для закалённых"}
    return {"code": "cold", "emoji": "🥶", "label": "холодно: купание для моржей"}


def _number(value, digits: int = 1) -> float | None:
    """Число из ответа модели или None: null/мусор не должны ломать вердикт."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), digits)


class SeaService:
    """Температура воды и волна по курортам с кэшем.

    Кэш дольше погодного (MARINE_TTL): волновую модель обновляют раз
    в 12 часов, температуру поверхности — раз в сутки, спрашивать чаще
    нечего.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}

    async def _fetch_point(
        self,
        client: httpx.AsyncClient,
        point_id: str,
        name: str,
        lat: float,
        lon: float,
    ) -> dict:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "sea_surface_temperature,wave_height",
            "timezone": "auto",
        }
        resp = await client.get(MARINE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        water = _number(current.get("sea_surface_temperature"))
        wave = _number(current.get("wave_height"))
        if water is None and wave is None:
            # Модель не покрывает точку (например, узкий пролив) — честная
            # недоступность вместо выдуманного «0 °C».
            return self._unavailable(point_id, name)
        return {
            "id": point_id,
            "name": name,
            "available": True,
            "water_temp": None if water is None else round(water),
            "wave_height": wave,
            "wave_label": wave_label(wave),
            "verdict": verdict(water, wave),
        }

    def _unavailable(self, point_id: str, name: str) -> dict:
        return {"id": point_id, "name": name, "available": False}

    async def get(self, city: str | None = None, refresh: bool = False) -> dict:
        now = time.time()
        wanted = SEA_POINTS
        if city:
            wanted = [p for p in SEA_POINTS if p[0] == city]
            if not wanted:
                raise KeyError(f"морская точка «{city}» не найдена")

        results: dict[str, dict] = {}
        stale: list[tuple] = []
        for p in wanted:
            hit = self._cache.get(p[0])
            if hit and now - hit[0] < MARINE_TTL and not refresh:
                results[p[0]] = hit[1]
            else:
                stale.append(p)

        if stale:
            async with httpx.AsyncClient(timeout=MARINE_HTTP_TIMEOUT) as client:
                gathered = await asyncio.gather(
                    *(self._fetch_point(client, p[0], p[1], p[2], p[3]) for p in stale),
                    return_exceptions=True,
                )
            # gather возвращает ровно по результату на точку — strict это фиксирует.
            for p, res in zip(stale, gathered, strict=True):
                if isinstance(res, Exception):
                    results[p[0]] = self._unavailable(p[0], p[1])
                else:
                    self._cache[p[0]] = (now, res)
                    results[p[0]] = res

        points = [results[p[0]] for p in wanted if p[0] in results]
        return {
            "online": any(p["available"] for p in points),
            "updated_at": datetime.now(UTC).astimezone().isoformat(),
            "warmest": self._warmest(points),
            "points": points,
        }

    @staticmethod
    def _warmest(points: list[dict]) -> dict | None:
        """Самая тёплая вода — единственная сводка, которая нужна туристу
        поверх списка. Нет данных — сводки нет."""
        known = [
            p for p in points if p.get("available") and p.get("water_temp") is not None
        ]
        if not known:
            return None
        best = max(known, key=lambda p: p["water_temp"])
        return {"id": best["id"], "name": best["name"], "temp": best["water_temp"]}


sea_service = SeaService()
