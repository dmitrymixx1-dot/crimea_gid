"""«Крым.Гид» — FastAPI + статичный SPA-фронт.

Запуск:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import APP_VERSION, STATIC_DIR
from .services.load import get_attractions, get_quiz
from .services.news import news_service
from .services.recommend import TAGS, TYPE_META, evaluate
from .services.weather import weather_service

app = FastAPI(title="Крым.Гид", version=APP_VERSION)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


class QuizIn(BaseModel):
    purpose: list[str] = Field(default_factory=list)
    season: str = "any"
    tempo: str = "medium"
    budget: str = "comfort"
    party: str = "solo"
    duration: str = "3-5"
    transport: str = "car"


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
        items = [a for a in items if q in a["name"].lower()
                 or q in a["description"].lower()]
    return {"count": len(items), "items": items}


@app.get("/api/attractions/{attraction_id}")
async def attraction_detail(attraction_id: str):
    """Одна точка каталога — нужна фронту для прямых ссылок #/place/<id>
    и внешним потребителям API."""
    for a in get_attractions():
        if a["id"] == attraction_id:
            return {**a, "type_meta": TYPE_META.get(
                a["type"], {"emoji": "📍", "label": a["type"], "img": "cat_nature.jpg"})}
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
async def news(limit: int = Query(40, ge=1, le=100),
               refresh: bool = False):
    data = await news_service.get(force=refresh)
    items = data["items"][:limit]
    out = dict(data)
    out["items"] = items
    return out


@app.get("/api/weather")
async def weather(city: str | None = None, refresh: bool = False):
    return await weather_service.get(city=city, refresh=refresh)


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
async def index():
    return FileResponse(STATIC_DIR / "index.html")
