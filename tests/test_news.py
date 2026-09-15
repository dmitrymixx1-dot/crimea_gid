import asyncio

from app import config
from app.services import news as news_mod
from app.services.news import NewsService, crimea_score, match_topics


def test_user_agent_is_ascii():
    # httpx кодирует header'ы latin-1 — кириллица в User-Agent ломает
    # конструктор клиента (регрессия: live-режим молча падал в офлайн).
    assert config.USER_AGENT.encode("latin-1")


def _get(svc, **kw):
    return asyncio.run(svc.get(**kw))


# ------------------- словари/классификация -------------------

def test_crimea_score_detects_cities():
    assert crimea_score("В Ялте открыли новый пляж") >= 2
    assert crimea_score("Керченский пролив: паромы") >= 2
    assert crimea_score("На Ай-Петри усилился шторм") >= 3


def test_crimea_score_ignores_kriminal():
    assert crimea_score("Суд рассмотрел криминальное дело в Москве") == 0


def test_crimea_score_ignores_other_kafa():
    # «кафа» в разговорной речи — кофейня, не Крым
    assert crimea_score("Открылась новая кафе на Невском") == 0


def test_topics_transport_and_beach():
    assert "transport" in match_topics("Новый график движения паромов на переправе")
    assert "beach" in match_topics("Купальный сезон на пляжах продлён")


def test_topics_history():
    assert "history" in match_topics("Археологи завершили раскопки в Херсонесе")


# ------------------- сборка ленты -------------------

def _service(monkeypatch, tmp_path, items=None, fail=False):
    svc = NewsService()
    svc._cache = {"ts": 0.0, "online": False, "items": [], "failed": []}
    calls = {"n": 0}

    async def fake_fetch(client, src):
        calls["n"] += 1
        if fail:
            raise RuntimeError("no network")
        return list(items or [])

    svc._fetch_feed = fake_fetch
    return svc, calls


def test_offline_fallback_to_snapshot(monkeypatch, tmp_path):
    svc, calls = _service(monkeypatch, tmp_path, fail=True)
    out = _get(svc, force=True)
    assert calls["n"] >= 1  # реально пытались опросить источники
    assert out["online"] is False
    assert out["total"] > 10
    assert out["crimea_total"] >= 10
    # крымские новости идут первыми
    assert out["items"][0]["crimea_score"] > 0
    # кэш на диске записан
    assert news_mod.config.NEWS_CACHE_FILE.exists()


def test_live_mode_dedupes_and_ranks_crimea_first(monkeypatch, tmp_path):
    items = [
        {"title": "Крым: новый фестиваль", "link": "http://x/1",
         "summary": "в Ялте", "published": "2026-09-15T10:00:00+03:00"},
        {"title": "Крым: новый фестиваль", "link": "http://x/2",
         "summary": "дубль с другой ленты", "published": "2026-09-14T10:00:00+03:00"},
        {"title": "Общая новость дня", "link": "http://x/3",
         "summary": "", "published": "2026-09-15T09:00:00+03:00"},
    ]
    svc, _ = _service(monkeypatch, tmp_path, items=items)
    out = _get(svc, force=True)
    assert out["online"] is True
    titles = [i["title"] for i in out["items"]]
    assert titles.count("Крым: новый фестиваль") == 1  # дедупликация между лентами
    assert out["items"][0]["title"] == "Крым: новый фестиваль"  # Крым — первым
    assert out["items"][0]["topics"]  # темы присвоены


def test_cache_ttl_prevents_refetch(monkeypatch, tmp_path):
    items = [{"title": "Крым: тест", "link": "http://x/1",
              "summary": "", "published": "2026-09-15T10:00:00+03:00"}]
    svc, calls = _service(monkeypatch, tmp_path, items=items)
    first = _get(svc, force=True)
    n1 = calls["n"]
    assert n1 == len(svc._sources)  # один запрос на каждую ленту
    second = _get(svc, force=False)
    assert calls["n"] == n1  # второй раз — из памяти, без запросов
    assert first["items"] == second["items"]
    third = _get(svc, force=True)
    assert calls["n"] == 2 * n1  # force — перечитали


def test_file_cache_restores_after_restart(monkeypatch, tmp_path):
    items = [{"title": "Крым: перезапуск", "link": "http://x/9",
              "summary": "", "published": "2026-09-15T11:00:00+03:00"}]
    svc, _ = _service(monkeypatch, tmp_path, items=items)
    _get(svc, force=True)
    assert news_mod.config.NEWS_CACHE_FILE.exists()

    # имитация рестарта: новый экземпляр подхватывает кэш с диска
    svc2 = NewsService()
    out = _get(svc2, force=False)
    assert any(i["title"] == "Крым: перезапуск" for i in out["items"])


def test_payload_shape(monkeypatch, tmp_path):
    svc, _ = _service(monkeypatch, tmp_path, fail=True)
    out = _get(svc, force=True)
    for key in ("online", "updated_at", "sources", "failed_sources",
                "total", "crimea_total", "items"):
        assert key in out
    item = out["items"][0]
    for key in ("id", "title", "link", "source", "published", "topics"):
        assert key in item
