"""Юнит-тесты морского сервиса (app/services/marine.py): купальный индекс.

Сеть не дёргаем: httpx-клиент подменяется фейком с ответом Open-Meteo
Marine, либо `_fetch_point` заглушается целиком.
"""

import asyncio
import math

import pytest

from app.services.marine import (
    SEA_IDS,
    SEA_POINTS,
    TEMP_COMFORT,
    TEMP_COOL,
    TEMP_OK,
    WAVE_DANGER,
    WAVE_ROUGH,
    SeaService,
    _meters,
    _number,
    verdict,
    wave_label,
)
from app.services.weather import CITIES

# --------------------------------------------------------------------------
# wave_label / _meters: подписи для человека
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "height,label",
    [
        (0.0, "штиль"),
        (0.29, "штиль"),
        (0.3, "лёгкая рябь"),
        (0.59, "лёгкая рябь"),
        (0.6, "небольшая волна"),
        (0.99, "небольшая волна"),
        (1.0, "заметное волнение"),
        (1.49, "заметное волнение"),
        (1.5, "сильное волнение"),
        (3.2, "сильное волнение"),
    ],
)
def test_wave_label_thresholds(height, label):
    assert wave_label(height) == label


def test_wave_label_without_data_is_empty():
    assert wave_label(None) == ""


def test_meters_uses_russian_decimal_comma():
    assert _meters(0.3) == "0,3"
    assert _meters(1.0) == "1,0"
    assert _meters(1.46) == "1,5"  # округление до десятых


# --------------------------------------------------------------------------
# verdict: купальный индекс
# --------------------------------------------------------------------------


def test_verdict_comfort_for_warm_water():
    v = verdict(24.0, 0.2)
    assert v["code"] == "comfort"
    assert v["emoji"] and v["label"]


@pytest.mark.parametrize(
    "temp,code",
    [
        (30.0, "comfort"),
        (TEMP_COMFORT, "comfort"),
        (22.9, "ok"),
        (TEMP_OK, "ok"),
        (19.9, "cool"),
        (TEMP_COOL, "cool"),
        (15.9, "cold"),
        (4.0, "cold"),
    ],
)
def test_verdict_temperature_bands(temp, code):
    assert verdict(temp, 0.1)["code"] == code


@pytest.mark.parametrize(
    "wave,code",
    [
        (WAVE_DANGER, "danger"),
        (2.4, "danger"),
        (1.4, "rough"),
        (WAVE_ROUGH, "rough"),
    ],
)
def test_verdict_wave_beats_warm_water(wave, code):
    """Тёплая вода не повод лезть в волну: безопасность выше удовольствия."""
    assert verdict(26.0, wave)["code"] == code


def test_verdict_mentions_measured_wave():
    assert "1,6 м" in verdict(26.0, 1.6)["label"]
    assert "1,2 м" in verdict(26.0, 1.2)["label"]


def test_verdict_without_water_data_is_honest():
    v = verdict(None, 0.4)
    assert v["code"] == "no_data"
    assert "нет данных" in v["label"]


def test_verdict_uses_raw_values_not_rounded():
    """22.6 °C — это ещё не 23 °C: показываем 23°, но вердикт по сырому
    значению (иначе порог съезжает на градус)."""
    svc = SeaService()
    point = _fetch_point(
        svc,
        _FakeClient(
            {
                "current": {
                    "sea_surface_temperature": 22.6,
                    "wave_height": 0.2,
                }
            }
        ),
    )
    assert point["water_temp"] == 23  # округление только для показа
    assert point["verdict"]["code"] == "ok"  # а вердикт — по 22.6


# --------------------------------------------------------------------------
# _number: мусор из модели не должен ломать вердикт
# --------------------------------------------------------------------------


def test_number_accepts_numbers():
    assert _number(22.64, 1) == 22.6
    assert _number(0, 1) == 0.0
    assert _number(2, 1) == 2.0


@pytest.mark.parametrize("bad", [None, "", "abc", [], {}, True, False])
def test_number_rejects_garbage(bad):
    """bool — подкласс int, но температурой не является."""
    assert _number(bad) is None


# --------------------------------------------------------------------------
# _fetch_point: разбор ответа Open-Meteo Marine
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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


MARINE_SAMPLE = {
    "current": {
        "time": "2026-09-17T12:00",
        "sea_surface_temperature": 23.4,
        "wave_height": 0.42,
    }
}


def _fetch_point(svc, client, point=("yalta", "Ялта", 44.485, 34.17)):
    return asyncio.run(svc._fetch_point(client, *point))


def test_fetch_point_parses_water_and_wave():
    point = _fetch_point(SeaService(), _FakeClient(MARINE_SAMPLE))
    assert point["available"] is True
    assert point["id"] == "yalta" and point["name"] == "Ялта"
    assert point["water_temp"] == 23
    assert point["wave_height"] == 0.4
    assert point["wave_label"] == "лёгкая рябь"
    assert point["verdict"]["code"] == "comfort"


def test_fetch_point_requests_marine_url_and_water_variables():
    svc = SeaService()
    client = _FakeClient(MARINE_SAMPLE)
    _fetch_point(svc, client)
    url, params = client.calls[0]
    assert url.endswith("/v1/marine")
    assert "sea_surface_temperature" in params["current"]
    assert "wave_height" in params["current"]
    assert params["latitude"] == 44.485
    assert params["longitude"] == 34.17


def test_fetch_point_without_any_values_is_unavailable():
    """Модель молчит по точке (например, узкий пролив) — не выдумываем 0 °C."""
    svc = SeaService()
    point = _fetch_point(svc, _FakeClient({"current": {}}))
    assert point == {"id": "yalta", "name": "Ялта", "available": False}


def test_fetch_point_temp_only_still_usable():
    payload = {"current": {"sea_surface_temperature": 21.0, "wave_height": None}}
    point = _fetch_point(SeaService(), _FakeClient(payload))
    assert point["available"] is True
    assert point["water_temp"] == 21
    assert point["wave_height"] is None
    assert point["wave_label"] == ""
    assert point["verdict"]["code"] == "ok"


# --------------------------------------------------------------------------
# SeaService.get: кэш, фильтр по точке, падение сети, сводка
# --------------------------------------------------------------------------


def _stub_fetch(avail=True, water=22.0, wave=0.3):
    calls = {"n": 0}

    async def fake(client, point_id, name, lat, lon):
        calls["n"] += 1
        if not avail:
            raise RuntimeError("no network")
        return {
            "id": point_id,
            "name": name,
            "available": True,
            "water_temp": round(water),
            "wave_height": wave,
            "wave_label": wave_label(wave),
            "verdict": verdict(water, wave),
        }

    return fake, calls


def _svc(fetch_fn):
    svc = SeaService()
    svc._fetch_point = fetch_fn  # заглушка вместо сети
    return svc


def test_get_returns_all_sea_points_by_default():
    fake, calls = _stub_fetch()
    out = asyncio.run(_svc(fake).get())
    assert out["online"] is True
    assert len(out["points"]) == len(SEA_POINTS)
    assert calls["n"] == len(SEA_POINTS)
    assert {p["id"] for p in out["points"]} == SEA_IDS


def test_get_filters_single_point():
    fake, calls = _stub_fetch()
    out = asyncio.run(_svc(fake).get(city="sudak"))
    assert [p["id"] for p in out["points"]] == ["sudak"]
    assert calls["n"] == 1


def test_get_unknown_point_raises_key_error():
    fake, _ = _stub_fetch()
    with pytest.raises(KeyError, match="gotham"):
        asyncio.run(_svc(fake).get(city="gotham"))


def test_cache_ttl_avoids_refetch():
    fake, calls = _stub_fetch()
    svc = _svc(fake)
    asyncio.run(svc.get(city="yalta"))
    asyncio.run(svc.get(city="yalta"))
    assert calls["n"] == 1


def test_refresh_forces_refetch():
    fake, calls = _stub_fetch()
    svc = _svc(fake)
    asyncio.run(svc.get(city="yalta"))
    asyncio.run(svc.get(city="yalta", refresh=True))
    assert calls["n"] == 2


def test_network_failure_marks_points_unavailable():
    fake, _ = _stub_fetch(avail=False)
    out = asyncio.run(_svc(fake).get(city="kerch"))
    assert out["online"] is False
    assert out["points"] == [{"id": "kerch", "name": "Керчь", "available": False}]
    assert out["warmest"] is None


def test_warmest_point_is_the_summary():
    async def fake(client, point_id, name, lat, lon):
        temp = {"yalta": 21.0, "kerch": 24.0, "sudak": 22.0}[point_id]
        return {
            "id": point_id,
            "name": name,
            "available": True,
            "water_temp": round(temp),
            "wave_height": 0.2,
            "wave_label": wave_label(0.2),
            "verdict": verdict(temp, 0.2),
        }

    out = asyncio.run(_svc(fake).get())
    assert out["warmest"]["id"] == "kerch"
    assert out["warmest"]["temp"] == 24
    assert out["warmest"]["name"] == "Керчь"


def test_warmest_ignores_points_without_water_temp():
    async def fake(client, point_id, name, lat, lon):
        if point_id == "yalta":
            return {"id": point_id, "name": name, "available": False}
        return {
            "id": point_id,
            "name": name,
            "available": True,
            "water_temp": None,
            "wave_height": 1.2,
            "wave_label": wave_label(1.2),
            "verdict": verdict(None, 1.2),
        }

    out = asyncio.run(_svc(fake).get())
    assert out["warmest"] is None  # температура воды неизвестна нигде


def test_payload_has_updated_at_with_timezone():
    fake, _ = _stub_fetch()
    out = asyncio.run(_svc(fake).get(city="yalta"))
    assert "T" in out["updated_at"] and "+" in out["updated_at"]


# --------------------------------------------------------------------------
# Список морских точек: согласован с курортами погоды
# --------------------------------------------------------------------------


def test_sea_points_are_unique_and_within_crimea():
    ids = [p[0] for p in SEA_POINTS]
    assert len(ids) == len(set(ids)), "дубликаты id в SEA_POINTS"
    assert len(SEA_POINTS) == 15
    for pid, name, lat, lon in SEA_POINTS:
        assert name
        assert 44.2 <= lat <= 45.7, f"{pid}: широта {lat}"
        assert 32.4 <= lon <= 36.7, f"{pid}: долгота {lon}"


def test_sea_points_reuse_weather_city_ids_and_names():
    """id морской точки — это id курорта погоды: фронт связывает их по id."""
    by_id = {c[0]: c[1] for c in CITIES}
    for pid, name, *_ in SEA_POINTS:
        assert pid in by_id, f"{pid}: нет такого курорта в CITIES"
        assert name == by_id[pid], f"{pid}: имя «{name}» ≠ «{by_id[pid]}»"


def test_inland_resorts_have_no_sea_points():
    """Симферополь, Бахчисарай и Белогорск не на море — точки для них
    не выдумываем. Тест ловит новый курорт в CITIES без решения по морю."""
    inland = {c[0] for c in CITIES} - SEA_IDS
    assert inland == {"simferopol", "bakhchisaray", "belogorsk"}


def _km(lat1, lon1, lat2, lon2):
    """Расстояние по равнопромежуточной проекции — точности теста хватает."""
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110.57
    return math.hypot(dx, dy)


def test_sea_points_are_offshore_but_near_their_city():
    """Точка обязана лежать в море (морская модель считает только воду),
    но рядом со своим городом, а не у соседа."""
    city = {c[0]: c for c in CITIES}
    for pid, _name, lat, lon in SEA_POINTS:
        _, _, clat, clon = city[pid]
        distance = _km(clat, clon, lat, lon)
        assert 1.0 <= distance <= 8.0, f"{pid}: {distance:.1f} км от города"


def test_sea_points_go_out_to_sea_not_inland():
    """Азимут от города — только в морскую сторону.

    Крым омывается Чёрным и Азовским морем, и для каждого курорта
    известно, куда смотреть: у Ялты море южнее, у Евпатории — западнее.
    """
    city = {c[0]: c for c in CITIES}
    # Ожидаемое направление выноса: (знак по широте, знак по долготе).
    expected = {
        "kerch": (0, -1),
        "shchelkino": (-1, 0),
        "feodosia": (-1, 0),
        "sudak": (-1, 1),
        "koktebel": (-1, 0),
        "yalta": (-1, 1),
        "gurzuf": (-1, 1),
        "partenit": (-1, 0),
        "alushta": (-1, 0),
        "alupka": (-1, 0),
        "simeiz": (-1, 0),
        "sevastopol": (-1, -1),
        "evpatoria": (0, -1),
        "saki": (0, -1),
        "chernomorskoe": (0, -1),
    }
    assert set(expected) == SEA_IDS, "направление выноса описано не для всех точек"
    for pid, _name, lat, lon in SEA_POINTS:
        _, _, clat, clon = city[pid]
        dlat, dlon = expected[pid]
        # Знак 0 — «вынос идёт не по этой оси», допускаем мелкое смещение.
        if dlat == 0:
            assert abs(lat - clat) <= 0.01, f"{pid}: ушёл по широте"
        else:
            assert abs(lat - clat) > 0.0005, f"{pid}: широта почти не изменилась"
            assert (lat - clat) * dlat > 0, f"{pid}: вынос по широте не в море"
        if dlon == 0:
            assert abs(lon - clon) <= 0.01, f"{pid}: ушёл по долготе"
        else:
            assert abs(lon - clon) > 0.0005, f"{pid}: долгота почти не изменилась"
            assert (lon - clon) * dlon > 0, f"{pid}: вынос по долготе не в море"
