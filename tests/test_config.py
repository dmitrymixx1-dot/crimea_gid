"""Юнит-тесты конфигурации (app/config.py)."""
import re

from app import config


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[a-z0-9.]+)?", config.APP_VERSION), \
        config.APP_VERSION


def test_defaults_are_sane(monkeypatch):
    import importlib
    for var in ("PORT", "NEWS_CACHE_TTL", "NEWS_HTTP_TIMEOUT",
                "WEATHER_TTL", "WEATHER_HTTP_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(config)  # читаем чистое окружение
    try:
        assert config.PORT == 8000
        assert config.NEWS_CACHE_TTL == 900       # 15 минут
        assert config.NEWS_HTTP_TIMEOUT == 10
        assert config.WEATHER_TTL == 3600
        assert config.WEATHER_HTTP_TIMEOUT == 8
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
