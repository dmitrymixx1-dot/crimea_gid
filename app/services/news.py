"""Сбор новостей: RSS-ленты источников + фильтрация по теме «Крым».

Сервис параллельно опрашивает все источники из ``sources.json``.
Если сеть недоступна (или все ленты упали), gracefully падает на
офлайн-снимок ``news_snapshot.json`` — фронт помечает это бейджем
«офлайн / демо-данные».
"""
import asyncio
import calendar
import html
import re
import time
from datetime import datetime, timezone

import feedparser
import httpx

from ..config import MAX_NEWS_ITEMS, NEWS_CACHE_TTL, NEWS_HTTP_TIMEOUT, USER_AGENT
from .load import get_snapshot, get_sources

# --------------------------------------------------------------------------
# Слова-маркеры Крыма (города, курорты, география). По одному совпадению
# даём 2 очка релевантности.
# --------------------------------------------------------------------------
CRIMEA_WORDS = {
    "крым", "крыма", "крыме", "крымский", "крымская", "крымское",
    "таврида", "таврический", "кафа",
    "севастополь", "севастополя", "симферополь", "симферополя",
    "керчь", "керченский", "ялта", "ялтинский", "ялтинской",
    "феодосия", "феодосийский", "судак", "судакской",
    "евпатория", "евпаторийский", "алушта", "алуштинский",
    "алупка", "гурзуф", "гаспра", "ореанда", "форос", "массандра",
    "коктебель", "ленино", "бахчисарай", "бахчисарайский",
    "черноморское", "демерджи", "инкерман", "мисхор", "херсонес",
    "старокрымск", "сарыч", "капчак", "лазурное", "миндальное",
    "джанкой", "белогорск", "нижнегорск", "красноперекопск",
    "перевальное", "санаторное", "сакский", "сасык", "голубая гавань",
}

# «крым*» по токенам (чтобы не ловить «криминал»).
_TOKEN_RE = re.compile(r"[а-яёa-z]+")
_HYPHEN_WORDS = {"ай-петри", "айпетри", "ай-дамир", "белбек"}

# --------------------------------------------------------------------------
# Правила классификации тем (идут в порядке приоритета).
# --------------------------------------------------------------------------
TOPIC_RULES = [
    ("safety", re.compile(
        r"предупрежд|опасн|эвакуац|мчс|штраф за|контроль|установили запр", re.I)),
    ("transport", re.compile(
        r"мост|паром|переправ|поезд|электричк|самол|аэропорт|автобус|"
        r"маршрутк|пробк|дорож|трасс|ремонт|движение|рейс|перевозк", re.I)),
    ("beach", re.compile(
        r"пляж|купан|купальный|море|волн|шторм|бу(е|и)|отдых|турист|сезон", re.I)),
    ("weather", re.compile(
        r"погод|дожд|ветер|жара|океан|градус|температур|осадк|солнц", re.I)),
    ("events", re.compile(
        r"фестиваль|праздник|ярмарк|концерт|откры(ли|тие|лась|ло)|старт|"
        r"завершил|закрыли|мастер-класс|спецпрограмм|фестив", re.I)),
    ("food", re.compile(
        r"вин|винодел|фермер|рынок|гастроном|кухн|сыр|десерт|импорт "
        r"продуктов|продукт|дегустац|конкурс", re.I)),
    ("history", re.compile(
        r"археолог|музей|дворец|крепост|истори|реставрац|памятн|"
        r"экспозиц|раскопк|монумент", re.I)),
]


def _clean_text(value: str, limit: int = 300) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def crimea_score(text: str) -> int:
    """Насколько новость про Крым: суммарное число совпадений маркеров."""
    t = " " + text.lower() + " "
    score = 0
    for w in CRIMEA_WORDS:
        if w in t:
            score += 2
    for w in _HYPHEN_WORDS:
        if w in t:
            score += 3
    for tok in _TOKEN_RE.findall(t):
        if tok.startswith("крым"):
            score += 3
    return score


def match_topics(text: str) -> list[str]:
    found = []
    for topic, pattern in TOPIC_RULES:
        if pattern.search(text):
            found.append(topic)
    return found[:3]


class NewsService:
    def __init__(self) -> None:
        self._sources = get_sources()
        self._cache: dict = {"ts": 0.0, "online": False, "items": [], "failed": []}

    # ------------------------------------------------------------------ fetch
    async def _fetch_feed(self, client: httpx.AsyncClient, src: dict) -> list[dict]:
        resp = await client.get(src["url"], follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries[:40]:
            title = _clean_text(entry.get("title", ""), 200)
            if not title:
                continue
            published = ""
            if entry.get("published_parsed"):
                published = datetime.fromtimestamp(
                    calendar.timegm(entry["published_parsed"]), tz=timezone.utc
                ).astimezone().isoformat()
            elif entry.get("published"):
                published = entry["published"]
            items.append({
                "title": title,
                "link": entry.get("link", src["url"]),
                "summary": _clean_text(entry.get("summary", "")),
                "published": published,
            })
        return items

    # ------------------------------------------------------------------- rank
    def _normalize(self, items: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for it in items:
            it = dict(it)
            it["crimea_score"] = crimea_score(
                f"{it['title']} {it.get('summary', '')}")
            it["topics"] = match_topics(
                f"{it['title']} {it.get('summary', '')}")
            key = re.sub(r"\W+", " ", it["title"].lower()).strip()[:80]
            if key in seen:
                # Дубликаты: оставляем то, что раньше по дате.
                if (it.get("published") or "") < (seen[key].get("published") or "9"):
                    seen[key] = it
                continue
            seen[key] = it
        out = list(seen.values())
        out.sort(
            key=lambda x: (not x["crimea_score"], x.get("published", "")),
            reverse=False,
        )
        # Крымские новости — первыми (внутри — по дате), затем остальные.
        crimea = [x for x in out if x["crimea_score"] > 0]
        rest = [x for x in out if x["crimea_score"] == 0]
        crimea.sort(key=lambda x: x.get("published", ""), reverse=True)
        rest.sort(key=lambda x: x.get("published", ""), reverse=True)
        for idx, item in enumerate(crimea + rest):
            item["id"] = f"n{idx}"
        return (crimea + rest)[:MAX_NEWS_ITEMS]

    def _snapshot_items(self) -> list[dict]:
        snap = get_snapshot()
        items = []
        for idx, raw in enumerate(snap.get("items", [])):
            item = dict(raw)
            item["id"] = f"s{idx}"
            item.setdefault("topics", match_topics(item.get("title", "")))
            items.append(item)
        return items

    # -------------------------------------------------------------------- get
    async def get(self, force: bool = False) -> dict:
        now = time.time()
        if not force and now - self._cache["ts"] < NEWS_CACHE_TTL:
            return self.payload()

        all_items: list[dict] = []
        failed: list[str] = []
        online = False
        try:
            async with httpx.AsyncClient(
                timeout=NEWS_HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml"},
            ) as client:
                results = await asyncio.gather(
                    *(self._fetch_feed(client, s) for s in self._sources),
                    return_exceptions=True,
                )
            for src, res in zip(self._sources, results):
                if isinstance(res, Exception):
                    failed.append(src["name"])
                else:
                    if res:
                        online = True
                    for it in res:
                        it["source"] = src["name"]
                        it["source_id"] = src["id"]
                    all_items.extend(res)
        except Exception:
            online = False
            failed = [s["name"] for s in self._sources]

        if online and all_items:
            items = self._normalize(all_items)
            self._cache = {"ts": now, "online": True, "failed": failed, "items": items}
        else:
            items = self._snapshot_items()
            self._cache = {
                "ts": now,
                "online": False,
                "failed": failed or [s["name"] for s in self._sources],
                "items": items,
            }
        return self.payload()

    def payload(self) -> dict:
        items = self._cache["items"]
        return {
            "online": self._cache["online"],
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "sources": [{"id": s["id"], "name": s["name"]} for s in self._sources],
            "failed_sources": self._cache["failed"],
            "total": len(items),
            "crimea_total": sum(1 for x in items if x.get("crimea_score", 0) > 0),
            "items": items,
        }


news_service = NewsService()
