"""Константы приложения «Крым.Гид»."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR.parent / "static"

# Как долго (в секундах) кэшируем результат опроса источников новостей.
NEWS_CACHE_TTL = 15 * 60
# Таймаут одного HTTP-запроса к RSS-ленте.
NEWS_HTTP_TIMEOUT = 10.0
# Сколько новостей максимум отдаём во внешнему миру.
MAX_NEWS_ITEMS = 80

USER_AGENT = (
    "CrimeaGuideBot/1.0 "
    "(туристический агрегатор новостей Крыма; FastAPI + feedparser)"
)

PORT = 8000
