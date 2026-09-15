"""Константы приложения «Крым.Гид».

Всё, что вынесено в переменные окружения, можно переопределить
без правки кода: PORT, NEWS_CACHE_TTL, NEWS_HTTP_TIMEOUT, WEATHER_TTL.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR.parent / "static"
# Файловый кэш последней успешной/кэшированной ленты (переживает рестарт).
NEWS_CACHE_FILE = DATA_DIR.parent.parent / "cache" / "news_cache.json"

PORT = int(os.environ.get("PORT", "8000"))

# Как долго (в секундах) держим результат опроса источников в памяти.
NEWS_CACHE_TTL = int(os.environ.get("NEWS_CACHE_TTL", str(15 * 60)))
# Таймаут одного HTTP-запроса к RSS-ленте.
NEWS_HTTP_TIMEOUT = float(os.environ.get("NEWS_HTTP_TIMEOUT", "10"))
# Сколько новостей максимум отдаём наружу.
MAX_NEWS_ITEMS = 80

# Погода: кэш прогноза (в секундах).
WEATHER_TTL = int(os.environ.get("WEATHER_TTL", str(60 * 60)))
WEATHER_HTTP_TIMEOUT = float(os.environ.get("WEATHER_HTTP_TIMEOUT", "8"))
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Заголовок должен быть ASCII (httpx кодирует header'ы ascii/latin-1).
USER_AGENT = (
    "CrimeaGuideBot/1.0 "
    "(tourism news aggregator for Crimea; FastAPI + feedparser)"
)

APP_VERSION = "0.9.1-beta"
