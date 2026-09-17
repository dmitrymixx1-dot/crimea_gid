"""«Крым.Гид» — FastAPI + статичный SPA-фронт.

Запуск:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import APP_VERSION, CSP, SITE_ORIGIN, STATIC_DIR
from .services.load import get_attractions, get_quiz
from .services.marine import SEA_IDS, sea_service
from .services.news import news_service
from .services.recommend import TAGS, TYPE_META, evaluate
from .services.weather import CITY_IDS, weather_service

app = FastAPI(title="Крым.Гид", version=APP_VERSION)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", CSP)
    return response


class QuizIn(BaseModel):
    """Ответы квиза. Допустимые значения — в точности `id` опций
    из `app/data/quiz.json` (согласованность закрыта тестом
    `test_data.py::test_quiz_options_match_quiz_model`);
    мусор отклоняется с 422, а не превращается в дефолты."""

    purpose: list[
        Literal[
            "beach",
            "nature",
            "history",
            "culture",
            "food",
            "wine",
            "active",
            "extreme",
            "family",
            "photo",
            "spa",
            "city",
            "view",
            "free",
            "romance",
        ]
    ] = Field(default_factory=list)
    season: Literal["summer", "autumn", "spring", "winter", "any"] = "any"
    tempo: Literal["relax", "medium", "active"] = "medium"
    budget: Literal["economy", "comfort", "premium"] = "comfort"
    party: Literal["solo", "couple", "family", "friends"] = "solo"
    duration: Literal["1-2", "3-5", "6-10", "10+"] = "3-5"
    transport: Literal["car", "transit"] = "car"


@app.get("/api/health")
async def health():
    return {"ok": True, "name": "Крым.Гид", "version": APP_VERSION}


@app.get("/api/tags")
async def tags():
    return {"tags": TAGS, "types": TYPE_META}


@app.get("/api/attractions")
async def attractions(
    tag: str | None = None,
    area: str | None = None,
    q: str | None = None,
):
    items = get_attractions()
    if tag:
        items = [a for a in items if tag in a["tags"]]
    if area:
        items = [a for a in items if a.get("area") == area]
    if q:
        q = q.lower()
        items = [
            a for a in items if q in a["name"].lower() or q in a["description"].lower()
        ]
    return {"count": len(items), "items": items}


@app.get("/api/attractions/{attraction_id}")
async def attraction_detail(attraction_id: str):
    """Одна точка каталога — нужна фронту для прямых ссылок #/place/<id>
    и внешним потребителям API."""
    for a in get_attractions():
        if a["id"] == attraction_id:
            fallback = {"emoji": "📍", "label": a["type"], "img": "cat_nature.jpg"}
            return {**a, "type_meta": TYPE_META.get(a["type"], fallback)}
    raise HTTPException(status_code=404, detail=f"место «{attraction_id}» не найдено")


@app.get("/api/areas")
async def areas():
    areas = sorted({a.get("area", "") for a in get_attractions()})
    return {"areas": [a for a in areas if a]}


@app.get("/api/quiz")
async def quiz():
    return get_quiz()


@app.post("/api/quiz/evaluate")
async def quiz_evaluate(payload: QuizIn):
    news = await news_service.get()
    result = evaluate(payload.model_dump(), news["items"])
    return result


@app.get("/api/news")
async def news(limit: int = Query(40, ge=1, le=100), refresh: bool = False):
    data = await news_service.get(force=refresh)
    items = data["items"][:limit]
    out = dict(data)
    out["items"] = items
    return out


@app.get("/api/weather")
async def weather(city: str | None = None, refresh: bool = False):
    if city is not None and city not in CITY_IDS:
        raise HTTPException(status_code=404, detail=f"город «{city}» не найден")
    return await weather_service.get(city=city, refresh=refresh)


@app.get("/api/sea")
async def sea(city: str | None = None, refresh: bool = False):
    """Купальный индекс: температура воды и волна у курортов.

    Купальный вердикт считает сервер (`services/marine.py`) — он не
    зависит от часового пояса устройства, в отличие от «открыто сейчас».
    """
    if city is not None and city not in SEA_IDS:
        # Разные причины 404 — разный текст: у Симферополя моря нет вовсе,
        # а «gotham» не город погоды.
        detail = (
            f"город «{city}» без выхода к морю"
            if city in CITY_IDS
            else f"морская точка «{city}» не найдена"
        )
        raise HTTPException(status_code=404, detail=detail)
    return await sea_service.get(city=city, refresh=refresh)


# --------------------------------------------------------------------------
# Статичный фронт (SPA)
# --------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/sw.js")
async def service_worker():
    """SW отдаём из корня, чтобы его scope был '/'
    (из /static/ он не управлял бы навигацией SPA)."""
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/")
async def index(request: Request):
    """SPA-каркас. Плейсхолдер `__ORIGIN__` в мета-тегах Open Graph
    подставляется фактическим origin'ом запроса (или SITE_ORIGIN из env):
    og:url/og:image обязаны быть абсолютными, а приложение живёт и за
    reverse-proxy, и на ephemeral-хостах."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    if "__ORIGIN__" in html:
        html = html.replace("__ORIGIN__", site_origin(request))
    return HTMLResponse(html)


def site_origin(request: Request) -> str:
    """Публичный origin: SITE_ORIGIN из env важнее заголовков запроса."""
    if SITE_ORIGIN:
        return SITE_ORIGIN.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    proto = proto.split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    host = host.split(",")[0].strip()
    return f"{proto}://{host}".rstrip("/")
