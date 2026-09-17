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

# Море: температура воды и волна. Кэш дольше погодного — волновую модель
# обновляют раз в 12 часов, температуру поверхности воды раз в сутки.
MARINE_TTL = int(os.environ.get("MARINE_TTL", str(3 * 60 * 60)))
MARINE_HTTP_TIMEOUT = float(os.environ.get("MARINE_HTTP_TIMEOUT", "8"))
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

# Заголовок должен быть ASCII (httpx кодирует header'ы ascii/latin-1).
USER_AGENT = (
    "CrimeaGuideBot/1.0 (tourism news aggregator for Crimea; FastAPI + feedparser)"
)

# Публичный origin сайта для Open Graph / Twitter Card (og:url, og:image
# обязаны быть абсолютными). Пусто — origin выводится из запроса
# (с учётом X-Forwarded-Proto/Host за reverse-proxy).
SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "").rstrip("/")

# Content-Security-Policy. Своих inline-скриптов нет (весь JS — файлы),
# поэтому script-src строго 'self'; inline остаются только style-атрибуты
# (ширина прогресс-бара и т.п.) — отсюда 'unsafe-inline' у style-src.
# frame-ancestors ослабляется через env, когда приложение встраивают
# в iframe (превью, витрины): CSP_FRAME_ANCESTORS="*".
CSP_FRAME_ANCESTORS = os.environ.get("CSP_FRAME_ANCESTORS", "'self'")
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    f"frame-ancestors {CSP_FRAME_ANCESTORS}"
)

APP_VERSION = "1.4.0"
