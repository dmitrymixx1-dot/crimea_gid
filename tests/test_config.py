"""Юнит-тесты конфигурации (app/config.py)."""

import re

from app import config


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[a-z0-9.]+)?", config.APP_VERSION), (
        config.APP_VERSION
    )


def test_defaults_are_sane(monkeypatch):
    import importlib

    for var in (
        "PORT",
        "NEWS_CACHE_TTL",
        "NEWS_HTTP_TIMEOUT",
        "WEATHER_TTL",
        "WEATHER_HTTP_TIMEOUT",
        "MARINE_TTL",
        "MARINE_HTTP_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(config)  # читаем чистое окружение
    try:
        assert config.PORT == 8000
        assert config.NEWS_CACHE_TTL == 900  # 15 минут
        assert config.NEWS_HTTP_TIMEOUT == 10
        assert config.WEATHER_TTL == 3600
        assert config.WEATHER_HTTP_TIMEOUT == 8
        # Море обновляют реже погоды: волновая модель — раз в 12 ч,
        # температура поверхности воды — раз в сутки.
        assert config.MARINE_TTL == 3 * 60 * 60
        assert config.MARINE_HTTP_TIMEOUT == 8
        assert config.MAX_NEWS_ITEMS > 0
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_paths_point_inside_repo():
    assert config.DATA_DIR.name == "data"
    assert config.DATA_DIR.exists()
    assert config.STATIC_DIR.name == "static"
    assert config.STATIC_DIR.exists()
    # NB: NEWS_CACHE_FILE в тестах подменён conftest на tmp_path —
    # проверяем лишь, что это json-файл.
    assert config.NEWS_CACHE_FILE.suffix == ".json"


def test_env_override(monkeypatch):
    """Переменные окружения переопределяют дефолты (через reimport)."""
    import importlib

    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("NEWS_CACHE_TTL", "5")
    importlib.reload(config)
    try:
        assert config.PORT == 9999
        assert config.NEWS_CACHE_TTL == 5
    finally:
        monkeypatch.undo()
        importlib.reload(config)  # вернуть дефолты для остальных тестов


def test_open_meteo_url():
    assert config.OPEN_METEO_URL.startswith("https://")
    assert "open-meteo.com" in config.OPEN_METEO_URL


def test_marine_url_is_open_meteo_marine():
    """Море — отдельный хост Open-Meteo Marine, ключа тоже не требует."""
    assert config.MARINE_URL.startswith("https://")
    assert "open-meteo.com" in config.MARINE_URL
    assert "/marine" in config.MARINE_URL
    assert config.MARINE_URL != config.OPEN_METEO_URL


def test_version_is_consistent_everywhere():
    """APP_VERSION — единый источник правды: README, sw.js и docs/api.md
    обязаны называть ту же версию (иначе PWA-кэш и доки врут)."""
    root = config.BASE_DIR.parent
    expected = config.APP_VERSION
    checks = [
        (root / "README.md", r"\*\*Версия ([\d.]+)\*\*"),
        (root / "static" / "sw.js", r'crimea-gid-v([\d.]+)"'),
        (root / "docs" / "api.md", r'"version": "([\d.]+)"'),
    ]
    for path, pattern in checks:
        found = set(re.findall(pattern, path.read_text(encoding="utf-8")))
        assert found == {expected}, f"{path.name}: {found} != {expected}"
