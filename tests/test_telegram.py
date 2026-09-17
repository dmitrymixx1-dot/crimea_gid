import asyncio

from app.services.news import NewsService, parse_telegram_page

TG_HTML = """
<div class="tgme_widget_message_wrap js-message_wrap">
  <div class="tgme_widget_message">
    <div class="tgme_widget_message_text js-message_text" dir="auto">В Ялте открыли новый фестиваль в парке. Он продлится три дня.</div>
    <span class="tgme_widget_message_date">
      <a href="/testchannel?before=123"><time datetime="2026-09-15T10:00:00+00:00">15 сен.</time></a>
    </span>
  </div>
</div>
<div class="tgme_widget_message_wrap js-message_wrap">
  <div class="tgme_widget_message">
    <div class="tgme_widget_message_text js-message_text" dir="auto"><a href="https://example.com">Ссылка</a> на новую трассу «Таврида»</div>
    <span class="tgme_widget_message_date">
      <a href="/testchannel?before=124"><time datetime="2026-09-14T09:00:00+00:00">14 сен.</time></a>
    </span>
  </div>
</div>
<div class="tgme_widget_message_wrap js-message_wrap">
  <div class="tgme_widget_message">
    <div class="tgme_widget_message_text js-message_text"></div>
    <span class="tgme_widget_message_date"><time datetime="2026-09-14T08:00:00+00:00"></time></span>
  </div>
</div>
"""


def test_telegram_parser_extracts_posts():
    items = parse_telegram_page(TG_HTML, "testchannel")
    assert len(items) == 2  # пустой третий пост отброшен
    first = items[0]
    assert first["link"] == "https://t.me/testchannel/123"
    assert first["published"] == "2026-09-15T10:00:00+00:00"
    assert "Ялте" in first["title"]
    # теги и сущности разобраны
    assert items[1]["title"].startswith("Ссылка на новую трассу")


def test_telegram_parser_empty_page():
    assert parse_telegram_page("<html><body>not a channel</body></html>", "x") == []


def test_telegram_source_flows_into_pipeline():
    svc = NewsService()
    svc._sources = [
        {
            "id": "tg1",
            "name": "Тестовый канал",
            "url": "https://t.me/s/testchannel",
            "type": "telegram",
        }
    ]
    svc._cache = {"ts": 0.0, "online": False, "items": [], "failed": []}

    async def fake(client, src):
        return parse_telegram_page(TG_HTML, "testchannel")

    svc._fetch_feed = fake
    out = asyncio.run(svc.get(force=True))
    assert out["online"] is True
    assert out["items"][0]["source"] == "Тестовый канал"
    assert out["crimea_total"] >= 1  # «Ялте» засчитано
    assert out["items"][0]["topics"]  # темы присвоены


def test_sources_mixed_types_load():
    from app.services.load import get_sources

    sources = get_sources()
    types = {s["type"] for s in sources}
    assert {"rss", "telegram"} <= types
