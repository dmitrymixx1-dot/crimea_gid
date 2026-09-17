"""Юнит-тесты сервиса погоды (app/services/weather.py).

Сеть не дёргаем: httpx-клиент подменяется фейком, отдающим фиксированный
ответ Open-Meteo, либо метод _fetch_city заглушается целиком.
"""

import asyncio
import os
import time

import pytest

from app.services.weather import (
    CITIES,
    HOURLY_HOURS,
    WEEKDAYS,
    WeatherService,
    _code_info,
    _number,
    hourly_window,
)

# --------------------------------------------------------------------------
# _code_info: WMO-коды → (эмодзи, подпись)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,emoji,label",
    [
        (0, "☀️", "ясно"),
        (1, "🌤️", "в основном ясно"),
        (3, "☁️", "пасмурно"),
        (61, "🌦️", "небольшой дождь"),
        (80, "🌦️", "небольшой ливень"),
        (95, "⛈️", "гроза"),
        (75, "❄️", "сильный снег"),
    ],
)
def test_code_info_known_codes(code, emoji, label):
    assert _code_info(code) == (emoji, label)


def test_code_info_unknown_code_falls_back():
    emoji, label = _code_info(1000)
    assert emoji == "🌡️"
    assert label == ""


def test_code_info_accepts_string_code():
    assert _code_info("0")[1] == "ясно"


@pytest.mark.parametrize("bad", [None, "", "abc", []])
def test_code_info_garbage_is_safe(bad):
    assert _code_info(bad) == ("🌡️", "")


def test_weekdays_russian_order():
    assert WEEKDAYS == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


# --------------------------------------------------------------------------
# _fetch_city: разбор ответа Open-Meteo
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Минимальный stand-in для httpx.AsyncClient.get."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResponse(self._payload)


OPEN_METEO_SAMPLE = {
    "current": {
        "temperature_2m": 21.6,
        "weather_code": 1,
        "wind_speed_10m": 12.4,
    },
    "daily": {
        "time": ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"],
        "weather_code": [1, 2, 61, 3],
        "temperature_2m_max": [26.4, 25.0, 19.6, 21.2],
        "temperature_2m_min": [17.2, 16.8, 14.1, 15.0],
    },
}


def _fetch(svc, client, city=("yalta", "Ялта", 44.49, 34.16)):
    return asyncio.run(svc._fetch_city(client, *city))


def test_fetch_city_parses_current():
    svc = WeatherService()
    out = _fetch(svc, _FakeClient(OPEN_METEO_SAMPLE))
    assert out["available"] is True
    assert out["id"] == "yalta" and out["name"] == "Ялта"
    assert out["current"]["temp"] == 22  # 21.6 → округление
    assert out["current"]["emoji"] == "🌤️"
    assert out["current"]["label"] == "в основном ясно"
    assert out["current"]["wind"] == 12  # 12.4 → округление


def test_fetch_city_includes_hourly_and_requests_it():
    svc = WeatherService()
    client = _FakeClient({**OPEN_METEO_SAMPLE, "hourly": _hourly_payload()})
    out = _fetch(svc, client)
    _, params = client.calls[0]
    assert "temperature_2m" in params["hourly"]
    assert "precipitation_probability" in params["hourly"]
    assert "weather_code" in params["hourly"]
    assert isinstance(out["hourly"], list)


def test_fetch_city_hourly_window_follows_current_time():
    svc = WeatherService()
    payload = {
        **OPEN_METEO_SAMPLE,
        "current": {**OPEN_METEO_SAMPLE["current"], "time": "2026-09-17T12:15"},
        "hourly": _hourly_payload(),
    }
    out = _fetch(svc, _FakeClient(payload))
    assert out["hourly"][0]["t"] == "2026-09-17T12:00"
    assert len(out["hourly"]) == HOURLY_HOURS


def test_fetch_city_sends_city_coordinates():
    svc = WeatherService()
    client = _FakeClient(OPEN_METEO_SAMPLE)
    _fetch(svc, client)
    _, params = client.calls[0]
    assert params["latitude"] == 44.49
    assert params["longitude"] == 34.16
    assert params["forecast_days"] == 4
    assert "weather_code" in params["daily"]


def test_fetch_city_forecast_days_rounding_and_codes():
    svc = WeatherService()
    out = _fetch(svc, _FakeClient(OPEN_METEO_SAMPLE))
    fc = out["forecast"]
    assert len(fc) == 4
    assert fc[0]["max"] == 26 and fc[0]["min"] == 17
    assert fc[2]["emoji"] == "🌦️"  # код 61 — небольшой дождь


def test_fetch_city_weekday_label_local_date():
    """День недели считается по локальной дате прогноза.

    Регрессия: naive-дата конвертировалась через astimezone(utc),
    и в поясах UTC+N подпись сдвигалась на день назад.
    """
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Moscow"
    time.tzset()
    try:
        svc = WeatherService()
        out = _fetch(svc, _FakeClient(OPEN_METEO_SAMPLE))
    finally:
        if old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = old_tz
        time.tzset()
    # 2026-09-17 — четверг и в UTC, и в Москве (и в любом поясе).
    assert out["forecast"][1]["day"] == "Чт"


def test_fetch_city_handles_short_daily_arrays():
    """Open-Meteo может вернуть меньше дней или пропустить значения."""
    payload = {
        "current": {"temperature_2m": 10.0, "weather_code": 3, "wind_speed_10m": 1.0},
        "daily": {
            "time": ["2026-09-16", "2026-09-17"],
            "weather_code": [3],
            "temperature_2m_max": [12.0],
            "temperature_2m_min": [],
        },
    }
    svc = WeatherService()
    out = _fetch(svc, _FakeClient(payload))
    assert len(out["forecast"]) == 2
    assert out["forecast"][1]["max"] is None
    assert out["forecast"][1]["min"] is None
    assert out["forecast"][1]["emoji"] == "🌡️"


# --------------------------------------------------------------------------
# hourly_window: почасовой прогноз от текущего часа города
# --------------------------------------------------------------------------


def _hourly_payload(hours=30, start_hour=10, day="2026-09-17"):
    """Ответ модели: часы подряд от start_hour, время локальное для города."""
    times, temps, codes, precips = [], [], [], []
    for i in range(hours):
        h = start_hour + i
        d, hh = day, h
        if h >= 24:  # переходим на следующие сутки
            d, hh = "2026-09-18", h - 24
        times.append(f"{d}T{hh:02d}:00")
        temps.append(20.0 + i * 0.5)  # половина градуса — есть что округлять
        codes.append(0 if i % 3 else 61)
        precips.append(50.0 if i % 2 == 0 else 5.0)
    return {
        "time": times,
        "temperature_2m": temps,
        "weather_code": codes,
        "precipitation_probability": precips,
    }


def test_hourly_window_starts_at_current_hour():
    """current.time = 12:15 — час 12:00 уже идёт, окно начинается с него."""
    hours = hourly_window(_hourly_payload(), "2026-09-17T12:15")
    assert hours[0]["t"] == "2026-09-17T12:00"
    assert len(hours) == HOURLY_HOURS == 24
    assert hours[-1]["t"] == "2026-09-18T11:00"


def test_hourly_window_rounds_temperature_and_precip():
    hours = hourly_window(_hourly_payload(), "2026-09-17T10:05")
    assert hours[0]["temp"] == 20
    assert hours[2]["temp"] == 21  # 21.0
    assert hours[1]["temp"] == 20  # 20.5 → банковское округление (как и в °C)
    assert hours[0]["precip"] == 50
    assert hours[1]["precip"] == 5
    assert hours[0]["emoji"] == "🌦️"  # код 61 — небольшой дождь
    assert hours[1]["emoji"] == "☀️"


def test_hourly_window_accepts_limit():
    hours = hourly_window(_hourly_payload(), "2026-09-17T10:05", limit=3)
    assert [h["t"] for h in hours] == [
        "2026-09-17T10:00",
        "2026-09-17T11:00",
        "2026-09-17T12:00",
    ]


def test_hourly_window_without_current_time_falls_back_to_start():
    """Модель не сказала, который час — отдаём прогноз как есть: окно
    по факту отсекает фронт по крымскому времени."""
    hours = hourly_window(_hourly_payload(), None)
    assert hours[0]["t"] == "2026-09-17T10:00"
    assert len(hours) == HOURLY_HOURS


def test_hourly_window_stale_forecast_is_empty():
    """current опережает прогноз (модель отстала) — пустой список честнее
    выдуманного «сейчас» на вчерашних часах."""
    assert hourly_window(_hourly_payload(), "2026-09-20T09:00") == []


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"time": []},
        {"time": "2026-09-17T10:00"},
        {"time": None},
    ],
)
def test_hourly_window_garbage_is_safe(bad):
    assert hourly_window(bad, "2026-09-17T12:15") == []


def test_hourly_window_survives_short_arrays():
    """Пропущенные значения — не повод падать: отдаём null и заглушку."""
    payload = {
        "time": ["2026-09-17T12:00", "2026-09-17T13:00"],
        "temperature_2m": [21.0],
        "weather_code": [],
        "precipitation_probability": [None, 40],
    }
    hours = hourly_window(payload, "2026-09-17T12:05")
    assert len(hours) == 2
    assert hours[1]["temp"] is None
    assert hours[1]["emoji"] == "🌡️"
    assert hours[1]["precip"] == 40
    assert hours[0]["precip"] is None


def test_hourly_window_ignores_garbage_values():
    payload = {
        "time": ["2026-09-17T12:00"],
        "temperature_2m": ["жарко"],
        "weather_code": [None],
        "precipitation_probability": [True],
    }
    hours = hourly_window(payload, "2026-09-17T12:05")
    assert hours[0]["temp"] is None
    assert hours[0]["precip"] is None  # bool — не вероятность осадков


@pytest.mark.parametrize("bad", [None, "", "abc", [], {}, True])
def test_number_rejects_garbage(bad):
    assert _number(bad) is None


def test_number_rounds_like_open_meteo_values():
    assert _number(20.44) == 20
    assert _number(20.5) == 20  # банковское округление Python, как и в °C
    assert _number(0) == 0


# --------------------------------------------------------------------------
# WeatherService.get: кэш, фильтр по городу, падение сети
# --------------------------------------------------------------------------


def _stub_fetch(avail=True):
    calls = {"n": 0}

    async def fake(client, city_id, name, lat, lon):
        calls["n"] += 1
        if not avail:
            raise RuntimeError("no network")
        return {
            "id": city_id,
            "name": name,
            "available": True,
            "current": {"temp": 20, "emoji": "☀️", "label": "ясно", "wind": 5},
            "forecast": [],
        }

    return fake, calls


def _svc(fetch_fn):
    svc = WeatherService()
    svc._fetch_city = fetch_fn  # заглушка вместо сети
    return svc


def test_get_returns_all_cities_by_default():
    fake, calls = _stub_fetch()
    out = asyncio.run(_svc(fake).get())
    assert out["online"] is True
    assert len(out["cities"]) == len(CITIES)
    assert calls["n"] == len(CITIES)  # один запрос на город
    assert {c["id"] for c in out["cities"]} == {c[0] for c in CITIES}


def test_get_filters_single_city():
    fake, calls = _stub_fetch()
    out = asyncio.run(_svc(fake).get(city="sudak"))
    assert [c["id"] for c in out["cities"]] == ["sudak"]
    assert calls["n"] == 1


def test_get_unknown_city_raises_key_error():
    """Неизвестный город — KeyError (на HTTP-слое превращается в 404)."""
    fake, _ = _stub_fetch()
    with pytest.raises(KeyError, match="gotham"):
        asyncio.run(_svc(fake).get(city="gotham"))


def test_cache_ttl_avoids_refetch():
    fake, calls = _stub_fetch()
    svc = _svc(fake)
    asyncio.run(svc.get(city="yalta"))
    assert calls["n"] == 1
    out = asyncio.run(svc.get(city="yalta"))  # попали в кэш
    assert calls["n"] == 1
    assert out["online"] is True


def test_refresh_forces_refetch():
    fake, calls = _stub_fetch()
    svc = _svc(fake)
    asyncio.run(svc.get(city="yalta"))
    asyncio.run(svc.get(city="yalta", refresh=True))
    assert calls["n"] == 2


def test_network_failure_marks_cities_unavailable():
    fake, _ = _stub_fetch(avail=False)
    out = asyncio.run(_svc(fake).get(city="kerch"))
    assert out["online"] is False
    assert out["cities"] == [{"id": "kerch", "name": "Керчь", "available": False}]


def test_payload_has_updated_at():
    fake, _ = _stub_fetch()
    out = asyncio.run(_svc(fake).get(city="yalta"))
    assert out["online"] is True
    # ISO-строка с таймзоной
    assert "T" in out["updated_at"] and "+" in out["updated_at"]


# --------------------------------------------------------------------------
# Список курортов
# --------------------------------------------------------------------------


def test_cities_are_unique_and_in_crimea():
    ids = [c[0] for c in CITIES]
    assert len(ids) == len(set(ids)), "дубликаты id в CITIES"
    assert len(CITIES) == 18
    for cid, name, lat, lon in CITIES:
        assert name
        assert 44.3 <= lat <= 45.7, f"{cid}: широта {lat}"
        assert 32.4 <= lon <= 36.7, f"{cid}: долгота {lon}"


def test_cities_cover_all_coasts():
    """Запад (Черноморское), восток (Щёлкино), центр и юг — все на месте."""
    got = {c[0] for c in CITIES}
    assert {"chernomorskoe", "shchelkino", "yalta", "kerch", "evpatoria"} <= got


def test_city_coordinates_match_catalog():
    """Координаты курорта и одноимённой точки каталога не разъезжаются."""
    from app.services.load import get_attractions

    by_id = {a["id"]: a for a in get_attractions()}
    for cid, _name, lat, lon in CITIES:
        a = by_id.get(cid)
        if not a:
            continue
        assert abs(a["lat"] - lat) < 0.02, f"{cid}: широта"
        assert abs(a["lng"] - lon) < 0.02, f"{cid}: долгота"
