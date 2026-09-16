"""Сбор новостей: RSS-ленты источников + фильтрация по теме «Крым».

Сервис параллельно опрашивает все источники из ``sources.json``.
Если сеть недоступна (или все ленты упали), gracefully падает на
офлайн-снимок ``news_snapshot.json`` — фронт помечает это бейджем
«офлайн / демо-данные».
"""
import asyncio
import calendar
import html
import json
import re
import time
from datetime import UTC, datetime

import feedparser
import httpx

from .. import config
from ..config import MAX_NEWS_ITEMS, NEWS_CACHE_TTL, NEWS_HTTP_TIMEOUT, USER_AGENT
from .load import get_snapshot, get_sources

# --------------------------------------------------------------------------
# Слова-маркеры Крыма (города, курорты, география). По одному совпадению
# даём 2 очка релевантности.
# --------------------------------------------------------------------------
CRIMEA_WORDS = {
    "крым", "крыма", "крыме", "крымский", "крымская", "крымское", "крымчан",
    "севастополь", "севастополя", "севастополе", "севастопольский",
    "симферополь", "симферополя", "симферополе", "симферопольский",
    "керчь", "керчи", "керченский", "керченская",
    "ялта", "ялты", "ялте", "ялтинский", "ялтинской",
    "феодосия", "феодосии", "феодосийский",
    "судак", "судака", "судаке", "судакский", "судакской",
    "евпатория", "евпатории", "евпаторийский",
    "алушта", "алушты", "алуште", "алуштинский",
    "алупка", "алупки", "алупке",
    "гурзуф", "гурзуфа", "гурзуфе",
    "гаспра", "ореанда", "ореанды", "ореанде",
    "форос", "фороса", "форосе",
    "массандра", "массандры", "массандре",
    "коктебель", "коктебеля", "коктебельский",
    "бахчисарай", "бахчисарая", "бахчисарае", "бахчисарайский",
    "черноморское", "черноморский", "демерджи",
    "инкерман", "инкермана", "инкермане",
    "мисхор", "мисхора", "мисхоре",
    "херсонес", "херсонеса", "херсонесе",
    "старокрымск",  # подстрока: Старокрымск(ий/ая/ом)
    "сарыч", "капчак", "лазурное", "миндальное",
    "джанкой", "белогорск", "нижнегорск", "красноперекопск",
    "перевальное", "санаторное", "сакский", "сасык",
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


# ---------------- Telegram: публичные превью t.me/s/<канал> ----------------
def parse_telegram_page(page_html: str, channel: str) -> list[dict]:
    """Парсинг публичной ленты канала без API-ключа.

    t.me/s/<канал> отдаёт HTML с последними ~20 постами; каждый пост —
    <div class="tgme_widget_message_wrap"> с текстом и <time datetime=…>.
    """
    items: list[dict] = []
    chunks = re.split(r'<div class="tgme_widget_message_wrap', page_html)[1:]
    for chunk in chunks:
        m_time = re.search(r'<time datetime="([^"]+)"', chunk)
        m_link = re.search(
            r'href="(?:https?://t\.me/)?/?' + re.escape(channel) + r'\?before=(\d+)"',
            chunk)
        m_text = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            chunk, re.S)
        if not m_text:
            continue
        text = re.sub(r"<br\s*/?>", " ", m_text.group(1))
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(re.sub(r"\s+", " ", text)).strip()
        if len(text) < 10:  # пустые посты / картинки без подписи
            continue
        link = f"https://t.me/{channel}/{m_link.group(1)}" if m_link else f"https://t.me/{channel}"
        items.append({
            "title": text[:100] + ("…" if len(text) > 100 else ""),
            "link": link,
            "summary": text[:300],
            "published": m_time.group(1) if m_time else "",
        })
        if len(items) >= 20:
            break
    return items


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
        self._load_file_cache()

    # ------------------------------------------------------- file cache
    def _load_file_cache(self) -> None:
        """Подхватываем последнюю успешную ленту с диска (переживает рестарт)."""
        try:
            if not config.NEWS_CACHE_FILE.exists():
                return
            data = json.loads(config.NEWS_CACHE_FILE.read_text(encoding="utf-8"))
            if data.get("ts") and time.time() - data["ts"] < config.NEWS_CACHE_TTL * 4:
                self._cache = {
                    "ts": data["ts"],
                    "online": data.get("online", False),
                    "failed": data.get("failed", []),
                    "items": data.get("items", []),
                }
        # Битый/отсутствующий файловый кэш — не ошибка: просто идём в сеть.
        except Exception:  # noqa: BLE001, S110
            pass

    def _save_file_cache(self) -> None:
        try:
            config.NEWS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            config.NEWS_CACHE_FILE.write_text(
                json.dumps({
                    "ts": self._cache["ts"],
                    "online": self._cache["online"],
                    "failed": self._cache["failed"],
                    "items": self._cache["items"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        # Не смогли сохранить кэш (ro-диск и т.п.) — лента всё равно отдаётся.
        except Exception:  # noqa: BLE001, S110
            pass

    # ------------------------------------------------------------------ fetch
    async def _fetch_feed(self, client: httpx.AsyncClient, src: dict) -> list[dict]:
        if src.get("type") == "telegram":
            channel = src["url"].rsplit("/", 1)[-1].strip()
            resp = await client.get(
                f"https://t.me/s/{channel}", follow_redirects=True)
            resp.raise_for_status()
            items = parse_telegram_page(resp.text, channel)
            if not items:
                raise RuntimeError(f"телеграм-канал «{channel}» пуст или недоступен")
            return items
        return await self._fetch_rss(client, src)

    async def _fetch_rss(self, client: httpx.AsyncClient, src: dict) -> list[dict]:
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
                    calendar.timegm(entry["published_parsed"]), tz=UTC
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
            # gather возвращает ровно по результату на источник — strict фиксирует это.
            for src, res in zip(self._sources, results, strict=True):
                if isinstance(res, Exception):
                    failed.append(src["name"])
                else:
                    if res:
                        online = True
                    for it in res:
                        it["source"] = src["name"]
                        it["source_id"] = src["id"]
                    all_items.extend(res)
        # Любой сбой опроса (сеть, DNS, SSL) — штатный офлайн-режим со снапшотом.
        except Exception:  # noqa: BLE001
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
        self._save_file_cache()
        return self.payload()

    def payload(self) -> dict:
        items = self._cache["items"]
        return {
            "online": self._cache["online"],
            "updated_at": datetime.now(UTC).astimezone().isoformat(),
            "sources": [{"id": s["id"], "name": s["name"]} for s in self._sources],
            "failed_sources": self._cache["failed"],
            "total": len(items),
            "crimea_total": sum(1 for x in items if x.get("crimea_score", 0) > 0),
            "items": items,
        }


news_service = NewsService()
