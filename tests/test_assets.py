"""Аудит статики (фаза 0.12.0): вес картинок, CSP-совместимая разметка,
согласованность PWA-оболочки. Тесты читают файлы напрямую, сеть не нужна.

Бюджеты веса зеркалят `tools/optimize_images.py`: картинки ужали
ресайзом и качеством, тесты не дают им «растолстеть» обратно.
"""

import json
import re

from app.config import APP_VERSION, STATIC_DIR
from app.services.load import get_attractions, get_sources

FRONT_FILES = [
    "index.html",
    "app.js",
    "plan-link.js",
    "catalog-link.js",
    "favs-link.js",
    "hourly.js",
    "rate-limit.js",
    "i18n.js",
    "sw.js",
]

BUDGET_HERO = 220_000  # байт
BUDGET_CAT = 130_000
BUDGET_TOTAL = 1_300_000


def read(name):
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def jpeg_size(path):
    """(ширина, высота) из SOF-фрейма JPEG — без сторонних зависимостей."""
    data = path.read_bytes()
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h = int.from_bytes(data[i + 5 : i + 7], "big")
            w = int.from_bytes(data[i + 7 : i + 9], "big")
            return w, h
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    raise AssertionError(f"не найден SOF-фрейм: {path}")


# ---------------- вес и размеры картинок ----------------


def test_image_weight_budget():
    hero = STATIC_DIR / "img" / "hero.jpg"
    assert hero.stat().st_size <= BUDGET_HERO, hero.stat().st_size
    for p in sorted((STATIC_DIR / "img").glob("cat_*.jpg")):
        assert p.stat().st_size <= BUDGET_CAT, f"{p.name}: {p.stat().st_size}"
    total = sum(p.stat().st_size for p in (STATIC_DIR / "img").iterdir())
    assert total <= BUDGET_TOTAL, total


def test_images_are_downsized_for_their_slots():
    """Hero показывается во всю ширину (≤1120 px), карточки — до 560 px:
    исходники 1536 px были чисто потраченными байтами."""
    w, _ = jpeg_size(STATIC_DIR / "img" / "hero.jpg")
    assert 1000 <= w <= 1400, w
    for p in sorted((STATIC_DIR / "img").glob("cat_*.jpg")):
        w, _ = jpeg_size(p)
        assert 640 <= w <= 900, f"{p.name}: {w}"


def test_hero_is_high_priority_without_inline_handlers():
    app = read("app.js")
    hero_tag = next(t for t in re.findall(r"<img\b[^>]*>", app) if "hero.jpg" in t)
    assert 'fetchpriority="high"' in hero_tag
    assert "onerror" not in hero_tag  # аварии картинок — делегированный обработчик


# ---------------- CSP-совместимая разметка ----------------


def test_no_inline_event_handlers_in_frontend():
    """CSP `script-src 'self'` запрещает inline-обработчики:
    ни одного on…= в шаблонах и каркасе."""
    events = r"(error|load|click|change|input|submit|focus|blur)"
    pattern = re.compile(r"\son" + events + r"\s*=", re.I)
    for name in FRONT_FILES:
        assert not pattern.search(read(name)), name


def test_all_scripts_in_index_are_external():
    tags = re.findall(r"<script\b[^>]*>", read("index.html"))
    assert tags, "скрипты вообще пропали из каркаса"
    for tag in tags:
        assert "src=" in tag, tag


def test_every_img_in_templates_has_meaningful_alt():
    app = read("app.js")
    tags = re.findall(r"<img\b[^>]*>", app, re.S)
    assert tags
    for tag in tags:
        assert re.search(r'alt="[^"]+"', tag), tag  # непустой alt у каждой
    assert 'alt=""' not in app
    assert 'alt=""' not in read("index.html")


def test_no_javascript_urls():
    for name in FRONT_FILES:
        assert "javascript:" not in read(name).lower(), name


# ---------------- согласованность оболочки ----------------


def test_manifest_mentions_real_catalog_size():
    m = json.loads(read("manifest.webmanifest"))
    assert str(len(get_attractions())) in m["description"], m["description"]


def test_footer_attribution_matches_real_sources():
    """Вывеска в футере называет источники и внешние сервисы — значит, она
    обязана совпадать с `sources.json`, а не оставаться в том виде, в каком
    её написали при трёх лентах. Про OSM отдельно: тайлы карты требуют
    указания авторства, и футер — то место, где оно живёт всегда, а не
    только во включённом слое Leaflet.

    Числа ищем по «число + начало слова»: склонение («4 телеграм-канала»,
    «5 телеграм-каналов») тест ломать не должно. Английская вывеска сверяется
    с тем же источником — иначе EN-пакет уедет в свою сторону.
    """
    sources = get_sources()
    rss = sum(1 for s in sources if s["type"] == "rss")
    tg = sum(1 for s in sources if s["type"] == "telegram")
    assert rss and tg, "лента без RSS или без телеграма — атрибуция врёт"

    footer = re.search(r"<footer.*?</footer>", read("index.html"), re.S).group(0)
    for word, expected in (("RSS", rss), ("телеграм", tg)):
        found = re.search(rf"(\d+)\s+{word}", footer)
        assert found, f"в футере нет числа перед «{word}»: {footer}"
        assert int(found.group(1)) == expected, (
            f"{word}: {found.group(1)} != {expected}"
        )
    for service in ("Open-Meteo", "OpenStreetMap"):
        assert service in footer, f"в футере не назван {service}"

    en = json.loads(read("i18n/en.json"))
    line = next(v for k, v in en["ui"].items() if k.startswith("Новости: "))
    for word, expected in (("RSS", rss), ("Telegram", tg)):
        found = re.search(rf"(\d+)\s+{word}", line)
        assert found and int(found.group(1)) == expected, f"EN {word}: {line}"
    for service in ("Open-Meteo", "OpenStreetMap"):
        assert service in line, f"в английской вывеске нет {service}: {line}"


def test_index_connects_catalog_link_module():
    html = read("index.html")
    assert 'src="/static/catalog-link.js"' in html
    assert 'src="/static/plan-link.js"' in html


def test_index_connects_i18n_before_app():
    """Модуль локализации обязан встать до `app.js`: оттуда берут `I18n.t`."""
    html = read("index.html")
    scripts = re.findall(r'<script src="(/static/[^"]+)"', html)
    assert "/static/i18n.js" in scripts
    assert scripts.index("/static/i18n.js") < scripts.index("/static/app.js")
    assert 'id="lang-toggle"' in html, "кнопки переключения речи нет в каркасе"
    # Кнопка — значок в шапке: без состояния «включено» она выглядела бы
    # декоративной.
    css = read("style.css")
    assert '#lang-toggle[aria-pressed="true"]' in css
    assert "#lang-toggle:hover" in css


def test_sw_shell_covers_umd_modules():
    sw = read("sw.js")
    assert '"/static/catalog-link.js"' in sw
    assert '"/static/plan-link.js"' in sw
    # Модуль речи — часть оболочки, а сам английский пакет — нет: его качает
    # только англичанин, и офлайн-первый-визит честно остаётся русским.
    assert '"/static/i18n.js"' in sw
    assert '"/static/i18n/en.json"' not in sw  # комментарий про него — не путь в SHELL
    # сырой index.html с плейсхолдером __ORIGIN__ в precache не нужен:
    # оболочка кеширует отрендеренный ответ GET /
    assert '"/static/index.html"' not in sw
    assert f"crimea-gid-v{APP_VERSION}" in sw


def test_place_deeplink_localizes_catalog_chrome():
    """`#/place/<id>` выходит из роутера раньше общего localize() — и всё
    равно обязан перевести шапку каталога, пока модалка переводит себя."""
    app = read("app.js")
    block = re.search(r"if \(path\.startsWith\(\"place/\"\)\)(.*?)\n  \}", app, re.S)
    assert block, "ветка place/ пропала из роутера"
    assert "localize();" in block.group(1)


def test_news_skips_only_foreign_text():
    """Чужое (RSS-заголовок и анонс) обходчик не трогает, своё — переводит.

    `data-i18n="skip"` на всей карточке оставил бы по-русским и бейдж
    издания, и время, и темы: они-то как раз наши подписи.
    """
    app = read("app.js")
    block = app[
        app.index("function newsItemHTML") : app.index("function newsItemHTML") + 1600
    ]
    assert 'class="news-title" data-i18n="skip"' in block
    assert 'class="news-summary" data-i18n="skip"' in block
    assert '<div class="news-item" data-i18n="skip">' not in block


def test_news_warns_the_english_reader_about_foreign_headlines():
    """Чужие заголовки не переводятся — и об этом сказано до чтения.

    Оговорка нужна только английскому экрану: русский читает ленту
    в оригинале, и предупреждать его не о чем.
    """
    app = read("app.js")
    assert "function foreignHeadlinesNote()" in app
    block = app[
        app.index("function foreignHeadlinesNote()") : app.index(
            "function newsItemHTML"
        )
    ]
    assert 'state.lang !== "en"' in block, "оговорка показывается не только англичанину"
    assert 't("Заголовки остаются русскими' in block, "строка мимо словаря"
    assert "${foreignHeadlinesNote()}" in app, "оговорка не вставляется в ленту"


def test_catalog_link_module_is_umd():
    src = read("catalog-link.js")
    assert "module.exports" in src and "root.CatalogLink" in src


def test_i18n_module_is_umd():
    src = read("i18n.js")
    assert "module.exports" in src and "root.I18n" in src


# ---------------- деплой-конфигурация (фаза 1.0) ----------------


def test_compose_serves_app_behind_caddy():
    """docker-compose.yml — прод-схема: приложение наружу не торчит,
    HTTPS терминирует Caddy, кэш ленты лежит в именованном томе."""
    import yaml

    root = STATIC_DIR.parent
    compose = yaml.safe_load((root / "docker-compose.yml").read_text("utf-8"))
    app_svc, caddy = compose["services"]["app"], compose["services"]["caddy"]
    # Приложение доступно только внутри compose-сети.
    assert "ports" not in app_svc, "app не должен публиковать порт наружу"
    assert "8000" in app_svc["expose"]
    assert any("80:80" in p for p in caddy["ports"])
    assert any("443:443" in p for p in caddy["ports"])
    # Кэш и сертификаты переживают пересоздание контейнеров.
    assert {"news-cache", "caddy-data"} <= set(compose["volumes"])
    assert any("/srv/cache" in v for v in app_svc["volumes"])


def test_compose_requires_domain_and_acme_email():
    """Без домена и почты ACME деплой обязан падать сразу,
    а не выпускать сертификат на пустую строку."""
    root = STATIC_DIR.parent
    compose = (root / "docker-compose.yml").read_text("utf-8")
    assert "${DOMAIN:?" in compose
    assert "${ACME_EMAIL:?" in compose
    env = (root / ".env.example").read_text("utf-8")
    assert "DOMAIN=" in env and "ACME_EMAIL=" in env


def test_caddyfile_proxies_with_forwarded_headers():
    """og:url собирается из X-Forwarded-*, когда SITE_ORIGIN пуст —
    прокси обязан их передавать."""
    caddy = (STATIC_DIR.parent / "deploy" / "Caddyfile").read_text("utf-8")
    assert "reverse_proxy app:8000" in caddy
    assert "X-Forwarded-Proto" in caddy and "X-Forwarded-Host" in caddy
    assert "/api/health" in caddy  # проверка живости бэкенда
    assert "Strict-Transport-Security" in caddy
    # Service worker не должен залипать в кэше прокси.
    assert "/sw.js" in caddy and "no-cache" in caddy


def test_env_secrets_are_not_committed():
    root = STATIC_DIR.parent
    assert not (root / ".env").exists(), ".env не место в репозитории"
    assert ".env" in (root / ".gitignore").read_text("utf-8")
    assert ".env" in (root / ".dockerignore").read_text("utf-8")


def test_backup_scripts_are_executable_and_sane():
    import os

    deploy = STATIC_DIR.parent / "deploy"
    for name in ("backup-cache.sh", "restore-cache.sh"):
        path = deploy / name
        assert path.exists(), name
        assert os.access(path, os.X_OK), f"{name}: нет бита исполнения"
        src = path.read_text("utf-8")
        assert src.startswith("#!/usr/bin/env bash"), name
        assert "set -euo pipefail" in src, name
        assert "/srv/cache" in src, name


# ---------------- порционный показ каталога (фаза 1.1) ----------------


def test_catalog_page_module_is_umd_and_precached():
    src = read("catalog-page.js")
    assert "module.exports" in src and "root.CatalogPage" in src
    assert '"/static/catalog-page.js"' in read("sw.js")
    assert 'src="/static/catalog-page.js"' in read("index.html")


def test_catalog_renders_a_first_page_not_the_whole_list():
    """60 карточек одним куском — дорогой первый рендер на слабом
    телефоне. Сетка обязана рисовать порцию и догружать остальное."""
    app = read("app.js")
    assert "CatalogPage.firstPage" in app
    assert "CatalogPage.visible" in app
    # Кнопка догрузки — доступный путь без скролла и фолбэк для
    # браузеров без IntersectionObserver.
    assert "cat-more-btn" in app
    assert "IntersectionObserver" in app
    assert 'typeof IntersectionObserver === "undefined"' in app


def test_catalog_observer_is_disconnected_on_route_change():
    """«Часовой» исчезает вместе с разметкой каталога — наблюдатель
    обязан отключаться, иначе он утекает между маршрутами."""
    app = read("app.js")
    assert app.count("catObserver?.disconnect()") >= 2


def test_catalog_paging_state_is_not_shared_by_link():
    """Ссылка на подборку несёт фильтры, но не «докрученность»:
    получатель должен увидеть ту же выборку с начала."""
    assert "catShown" not in read("catalog-link.js")
    src = read("catalog-page.js")
    assert "buildCatalogQuery" not in src


def test_bind_cards_is_idempotent_for_paged_rendering():
    """Каталог догружается порциями и зовёт bindCards поверх уже
    связанных карточек. Без защиты избранное получило бы второй
    listener и переключалось бы дважды, то есть никак."""
    app = read("app.js")
    assert "data-bound" in app, "нет защиты от повторной привязки"
    assert "[data-fav]:not([data-bound])" in app
    assert ".card[data-id]:not([data-bound])" in app


def test_paged_catalog_appends_instead_of_full_repaint():
    """Догрузка дорисовывает порцию: полный перерендер съел бы весь
    выигрыш и сбрасывал бы фокус с кнопки."""
    app = read("app.js")
    assert "insertAdjacentHTML" in app
    assert "appendCatCards" in app


# ---------------- «открыто сейчас» (фаза 1.1) ----------------


def test_open_now_module_is_umd_and_wired():
    src = read("open-now.js")
    assert "module.exports" in src and "root.OpenNow" in src
    assert '"/static/open-now.js"' in read("sw.js")
    assert 'src="/static/open-now.js"' in read("index.html")


def test_open_now_uses_crimea_time_not_device_time():
    """Турист из Екатеринбурга должен видеть про ялтинский музей то же,
    что турист в Ялте: считаем в UTC+3, а не в поясе устройства."""
    src = read("open-now.js")
    assert "TZ_OFFSET_MIN = 3 * 60" in src
    assert "getTimezoneOffset" in src


def test_open_now_filter_keeps_places_without_schedule():
    """Пляж и мыс открыты всегда. Прятать их по кнопке «открыто сейчас»
    было бы враньём — фильтр убирает только заведомо закрытое."""
    src = read("open-now.js")
    assert "return !s.known || s.open;" in src
    app = read("app.js")
    assert "OpenNow.filterOpen" in app


def test_catalog_open_filter_has_a_disclaimer():
    """В расписании то, что закодировать нельзя (санитарные дни,
    непогода) — интерфейс обязан это признавать."""
    app = read("app.js")
    assert "cat-open" in app
    assert 'aria-pressed="${state.f.open}"' in app
    assert "уточняйте на месте" in app


# ---------------- шаринг избранного (фаза 1.2) ----------------


def test_favs_link_module_is_umd_and_wired():
    src = read("favs-link.js")
    assert "module.exports" in src and "root.FavsLink" in src
    assert '"/static/favs-link.js"' in read("sw.js")
    assert 'src="/static/favs-link.js"' in read("index.html")
    app = read("app.js")
    assert "FavsLink.favsUrl" in app
    assert "FavsLink.parseFavsQuery" in app
    # Кнопка шаринга есть только у непустого избранного.
    assert 'id="fav-share"' in app


def test_favs_link_imports_only_known_ids():
    """Получатель обязан видеть только те id, что есть в его каталоге.
    Импорт — однонаправленный (только add): своё избранное ссылка не
    чистит; логика — в parseFavsQuery (JS-тесты), здесь фиксируем
    место сверки с каталогом."""
    src = read("favs-link.js")
    assert "known.has(id)" in src
    app = read("app.js")
    assert "state.attractions.map(a => a.id)" in app
    assert "state.favs.add(id)" in app


# ---------------- море и купальный индекс (фаза 1.3) ----------------


def test_home_renders_sea_block_next_to_weather():
    app = read("app.js")
    assert "weatherStrip()" in app and "seaStrip()" in app
    assert 'api("/api/sea")' in app, "морской блок нечем наполнять"


def test_bathing_verdict_is_computed_server_side():
    """Пороги купального индекса — в app/services/marine.py (там их
    проверяет `test_sea.py`). Вторая копия правил во фронте означала бы
    расхождение вердикта и данных, поэтому её здесь быть не должно."""
    app = read("app.js")
    assert "p.verdict.code" in app, "фронт обязан рисовать серверный вердикт"
    for name in ("WAVE_DANGER", "WAVE_ROUGH", "TEMP_COMFORT"):
        assert name not in app, f"{name}: правила продублированы во фронте"


def test_sea_block_does_not_invent_missing_wave():
    """Модель может отдать только температуру воды — волну не выдумываем."""
    app = read("app.js")
    assert "волна: нет данных" in app


def test_sea_block_has_an_honest_disclaimer():
    """Морская модель считает воду в открытом море: у берега может быть
    иначе, и об этом надо сказать честно."""
    app = read("app.js")
    assert "морская модель" in app.lower()
    assert "оборудованных пляжах" in app


# ---------------- почасовой прогноз (фаза 1.4) ----------------


def test_hourly_module_is_umd_and_wired():
    src = read("hourly.js")
    assert "module.exports" in src and "root.Hourly" in src
    assert '"/static/hourly.js"' in read("sw.js")
    assert 'src="/static/hourly.js"' in read("index.html")
    assert "Hourly.next" in read("app.js")


def test_hourly_window_uses_crimea_time_like_open_now():
    """Ответ API живёт в кэше до часа: «сейчас» отсчитывает клиент,
    и считает он по Крыму, а не по поясу устройства."""
    src = read("hourly.js")
    assert "TZ_OFFSET_MIN = 3 * 60" in src
    assert "getTimezoneOffset" in src
    app = read("app.js")
    assert "Hourly.next(city.hourly, new Date())" in app


def test_hourly_block_is_native_details_without_js_toggle():
    """CSP запрещает inline-обработчики, а <details> даёт раскрытие
    бесплатно — вместе с клавиатурой и скринридерами."""
    app = read("app.js")
    assert '<details class="w-hours">' in app
    assert "<summary>По часам</summary>" in app
    # Раскрытие не требует обработчиков клика вокруг блока.
    block = app[app.index("function hourlyStrip") : app.index("function weatherStrip")]
    assert "addEventListener" not in block


def test_hourly_precip_hint_lives_in_the_module():
    """Порог «💧 от 30%» — правило модуля, а не строчка во фронте."""
    app = read("app.js")
    assert "precipLabel" in app
    block = app[app.index("function hourlyStrip") : app.index("function weatherStrip")]
    assert ">=" not in block.replace("h.precipLabel ?", "")  # порог не дублируется
    assert "PRECIP_HINT" in read("hourly.js")


# ---------------- интерактивная карта (фаза 1.5) ----------------


def test_leaflet_module_is_umd_and_wired():
    """Leaflet-обёртка — UMD-модуль в том же стиле, что и остальные,
    подключён в каркас и закэширован в оболочке PWA. Сам Leaflet
    (vendor/leaflet.js, vendor/leaflet.css) тоже в прекэше — мы не
    хотим тянуть его с CDN ради строгой CSP 'self'."""
    src = read("leaflet-map.js")
    assert "module.exports" in src and "root.LeafletMap" in src
    sw = read("sw.js")
    assert '"/static/leaflet-map.js"' in sw
    assert '"/static/vendor/leaflet.js"' in sw
    assert '"/static/vendor/leaflet.css"' in sw
    html = read("index.html")
    assert 'src="/static/leaflet-map.js"' in html
    assert "/static/vendor/leaflet.css" not in html  # стили грузит модуль лениво


def test_leaflet_vendor_files_are_present_locally():
    """Никаких CDN в src/href: всё для интерактивной карты лежит в
    static/vendor/ и раздаётся с нашего хоста (CSP img/connect-src
    разрешает только тайлы OSM по https)."""
    vendor = STATIC_DIR / "vendor"
    assert (vendor / "leaflet.js").exists(), "leaflet.js не скачан"
    assert (vendor / "leaflet.css").exists(), "leaflet.css не скачан"
    # Иконки маркеров Leaflet — из /static/vendor/images/, а не CDN.
    css = (vendor / "leaflet.css").read_text("utf-8")
    assert "url(/static/vendor/images/" in css, "пути к картинкам не поправлены"
    assert "unpkg.com" not in css and "jsdelivr" not in css and "cdnjs" not in css


def test_svg_map_is_default_leaflet_is_opt_in():
    """Родная SVG-схема — дефолт: работает без сети, не тянет тайлы.
    Интерактивный слой включается явно кнопкой. На случай неудачной
    загрузки Leaflet есть фолбэк на SVG."""
    app = read("app.js")
    assert 'mapLayer: "svg"' in app, "дефолтный слой — SVG"
    assert "switchMapLayer" in app
    assert "map-interactive" in app
    # Кнопка переключения — две кнопки: «Схема» и «Спутник/карта».
    assert 'data-layer="svg"' in app
    assert 'data-layer="leaflet"' in app
    # Leaflet не импортируется в глобальный скоуп каркаса (не растит
    # холодную загрузку на ~160 Кб): модуль подгружается при переключении.
    assert "/static/vendor/leaflet.js" not in read("index.html")


def test_csp_allows_osm_tiles_only_when_needed():
    """Политика разрешает тайлы OpenStreetMap для img-src и connect-src,
    но не открывает другие внешние хосты и не ослабляет script-src."""
    from app.config import CSP

    assert "script-src 'self'" in CSP, "script-src не должен ослабляться"
    assert "https://tile.openstreetmap.org" in CSP
    # OSM только в картинках и коннектах, а не в скриптах/стилях/фреймах.
    assert CSP.count("https://tile.openstreetmap.org") == 2
    # Внешних шрифтов/iframe-ов не появилось.
    assert "font-src 'self'" in CSP
    assert "object-src 'none'" in CSP


def test_leaflet_layer_recreates_markers_on_filter():
    """Маркеры Leaflet обязаны обновляться синхронно с фильтром по тегам
    и показом/скрытием маршрута плана — как это делает SVG-слой."""
    src = read("leaflet-map.js")
    assert "markers.clearLayers" in src, "старые маркеры не чистятся"
    assert "planLayer.clearLayers" in src, "план не перерисовывается"
    assert "options.showPlan" in src and "options.planStops" in src
    app = read("app.js")
    assert "LeafletMap.createOrUpdate" in app
    assert "state.mapShowPlan" in app  # флаг плана общий для обоих слоёв


def test_leaflet_failure_falls_back_to_svg():
    """Если загрузка тайлов или инициализация Leaflet сорвалась —
    пользователь возвращается на SVG-схему, а не видит пустой квадрат."""
    app = read("app.js")
    assert "catch(err" in app  # ошибка загрузки ловится
    assert 'switchMapLayer("svg")' in app  # откат на схему
    assert "Не удалось загрузить интерактивную карту" in app


# ---------------- лимиты и автодеплой (фаза 1.6) ----------------


def test_rate_limit_module_is_umd_and_wired():
    """Подписи 429 живут в модуле (как и остальные правила фронта):
    их можно покрыть тестами, а не держать в разметке."""
    src = read("rate-limit.js")
    assert "module.exports" in src and "root.RateLimit" in src
    assert '"/static/rate-limit.js"' in read("sw.js")
    assert 'src="/static/rate-limit.js"' in read("index.html")
    app = read("app.js")
    # Фронт читает Retry-After сервера, а не выдумывает время ожидания.
    assert 'res.headers.get("Retry-After")' in app
    assert "RateLimit.message" in app


def test_frontend_reads_the_budget_instead_of_waiting_for_429():
    """Бюджет у каждой ручки свой, и фронт его знает: гасит кнопку до
    открытия окна, а не выбивает второй 429 подряд."""
    app = read("app.js")
    assert "RateLimit.readBudget(res.headers)" in app
    # Бюджеты складываются по имени правила, а не в одну переменную.
    assert "state.budgets[budget.rule]" in app
    assert "function coolDown(" in app and "function freshBudget(" in app
    news_block = app[
        app.index("async function renderNews") : app.index("function renderNewsBody")
    ]
    assert 'freshBudget("news")' in news_block
    assert "function budgetHint()" in app
    assert 'budgetText(freshBudget("news"))' in app or "budgetHint()" in news_block
    # Квиз после отказа тоже отдыхает: повторный клик не тратит бюджет впустую.
    quiz_block = app[
        app.index("async function submitQuiz") : app.index("const SLOT_META")
    ]
    assert "coolDown(" in quiz_block


def test_frontend_knows_the_client_wide_ceiling():
    """Общий потолок клиента виден и фронту: кнопка гаснет по нему, а
    подпись у ленты не обещает обновлений, которые сервер уже не отдаст."""
    src = read("rate-limit.js")
    assert "X-RateLimit-Total-Remaining" in src, "модуль не читает потолок"
    assert "function readCeiling" in src and "CEILING_RULE" in src
    app = read("app.js")
    assert "RateLimit.readCeiling(res.headers)" in app
    assert "state.budgets[RateLimit.CEILING_RULE]" in app
    hint = app[app.index("function budgetHint()") : app.index("function apiErrorText")]
    assert "CEILING_RULE" in hint, "подпись ленты не смотрит на потолок"


def test_limit_budgets_are_documented_per_route():
    """Бюджеты видно и в докладе (`docs/api.md`), и в `.env.example`:
    настроить лимит, не зная, чей он, нельзя."""
    root = STATIC_DIR.parent
    api = (root / "docs" / "api.md").read_text(encoding="utf-8")
    for name in (
        "RATE_LIMIT_NEWS",
        "RATE_LIMIT_WEATHER",
        "RATE_LIMIT_SEA",
        "RATE_LIMIT_TOTAL",
    ):
        assert name in api, f"в docs/api.md нет {name}"
    assert "/api/limits" in api, "ручка со бюджетами не задокументирована"
    readme = (root / "README.md").read_text(encoding="utf-8")
    for name in (
        "RATE_LIMIT_NEWS",
        "RATE_LIMIT_WEATHER",
        "RATE_LIMIT_SEA",
        "RATE_LIMIT_TOTAL",
    ):
        assert name in readme, f"в README нет {name}"


def test_rate_limit_error_is_shown_instead_of_raw_status():
    """Квиз и «Обновить» новостей обязаны объяснять 429 по-человечески."""
    app = read("app.js")
    assert "apiErrorText" in app
    block = app[app.index("function submitQuiz") : app.index("const SLOT_META")]
    assert "apiErrorText" in block
    # Кнопка «Обновить» после 429 не должна оставаться мёртвой.
    news_block = app[
        app.index("async function renderNews") : app.index("function renderNewsBody")
    ]
    assert "btn.disabled = false" in news_block


def test_compose_trusts_its_own_proxy():
    """За Caddy адрес соединения — сам прокси: без TRUST_PROXY все гости
    делили бы один лимит на контейнер."""
    import yaml

    root = STATIC_DIR.parent
    compose = yaml.safe_load((root / "docker-compose.yml").read_text("utf-8"))
    env = compose["services"]["app"]["environment"]
    # compose сам подставит дефолт из `${VAR:-…}`; нам важно, что ручка
    # передаётся и что по умолчанию прокси считается своим.
    assert env["TRUST_PROXY"] == "${TRUST_PROXY:-1}"
    assert env["RATE_LIMIT_ENABLED"] == "${RATE_LIMIT_ENABLED:-1}"
    # Бюджет каждой refresh-ручки передаётся отдельно: в контейнере
    # лимиты не должны схлопываться в одно общее число.
    for var in (
        "RATE_LIMIT_QUIZ",
        "RATE_LIMIT_NEWS",
        "RATE_LIMIT_NEWS_WINDOW",
        "RATE_LIMIT_WEATHER",
        "RATE_LIMIT_WEATHER_WINDOW",
        "RATE_LIMIT_SEA",
        "RATE_LIMIT_SEA_WINDOW",
        # Общий потолок клиента: без него «по чуть-чуть с каждой ручки»
        # проходит в контейнере так же свободно, как и в dev.
        "RATE_LIMIT_TOTAL",
        "RATE_LIMIT_TOTAL_WINDOW",
    ):
        assert var in env, f"compose не передаёт {var}"


def test_env_example_documents_rate_limits():
    text = (STATIC_DIR.parent / ".env.example").read_text(encoding="utf-8")
    for var in (
        "RATE_LIMIT_ENABLED",
        "RATE_LIMIT_QUIZ",
        "RATE_LIMIT_NEWS",
        "RATE_LIMIT_NEWS_WINDOW",
        "RATE_LIMIT_WEATHER",
        "RATE_LIMIT_WEATHER_WINDOW",
        "RATE_LIMIT_SEA",
        "RATE_LIMIT_SEA_WINDOW",
        "RATE_LIMIT_TOTAL",
        "RATE_LIMIT_TOTAL_WINDOW",
        "TRUST_PROXY",
    ):
        assert var in text, f"в .env.example нет {var}"
    # Общая переменная осталась фолбэком для старых деплоев — и об этом
    # в файле сказано, а не просто «её больше нет».
    assert "RATE_LIMIT_REFRESH" in text and "фолбэк" in text


def deploy_workflow():
    import yaml

    path = STATIC_DIR.parent / ".github" / "workflows" / "deploy.yml"
    text = path.read_text("utf-8")
    return yaml.safe_load(text), text


def test_deploy_workflow_is_tag_driven_and_keyless():
    """Выкат — по тегу (или вручную), ключи и хосты — только в секретах."""
    wf, text = deploy_workflow()
    triggers = wf.get("on", wf.get(True))
    assert "v*" in triggers["push"]["tags"], "нет триггера на тег"
    assert "workflow_dispatch" in triggers
    for secret in (
        "DEPLOY_HOST",
        "DEPLOY_USER",
        "DEPLOY_PATH",
        "DEPLOY_SSH_KEY",
    ):
        assert f"secrets.{secret}" in text, secret
    assert "PRIVATE KEY" not in text, "ключ в репозитории быть не должно"
    assert "password" not in text
    # Сторонние экшены не тянем: только официальные actions/*.
    for step in wf["jobs"]["deploy"]["steps"]:
        uses = step.get("uses", "")
        if uses:
            assert uses.startswith("actions/"), uses


def test_deploy_workflow_checks_tests_before_ssh():
    """Не выкатываем тег, который не прошёл тесты: preflight раньше SSH."""
    steps = deploy_workflow()[0]["jobs"]["deploy"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    preflight = next(i for i, r in enumerate(runs) if "pytest" in r)
    ssh = next(i for i, r in enumerate(runs) if "ssh " in r)
    assert preflight < ssh


def test_deploy_workflow_does_not_run_two_deploys_at_once():
    wf = deploy_workflow()[0]
    assert wf["concurrency"]["group"] == "deploy"
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_deploy_workflow_skips_gracefully_without_a_server():
    """Релиз не должен краснеть из-за не подключённого сервера: когда
    секретов нет совсем, выкат пропускается с notice (workflow зелёный),
    а частичная настройка — по-прежнему ошибка. Шаги SSH гейтятся
    флагом DEPLOY_ENABLED, который выставляет проверка секретов."""
    steps = deploy_workflow()[0]["jobs"]["deploy"]["steps"]
    check = next(s for s in steps if s.get("name") == "Проверить секреты деплоя")
    run = check["run"]
    assert 'have" = "0"' in run and "выкат пропущен" in run
    assert "DEPLOY_ENABLED=true" in run
    assert 'echo "::error::не заданы секреты' in run
    for name in ("Настроить SSH", "Выкатить", "Что получилось"):
        step = next(s for s in steps if s.get("name") == name)
        # PyYAML 1.1 читает ключ `if:` как булев True — сверяем обе записи.
        guard = str(step.get("if", step.get(True, "")))
        assert "env.DEPLOY_ENABLED" in guard, name


def test_deploy_script_is_executable_and_sane():
    import os
    import re

    path = STATIC_DIR.parent / "deploy" / "deploy.sh"
    assert os.access(path, os.X_OK), "нет бита исполнения"
    src = path.read_text("utf-8")
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert "up -d --build" in src
    assert 'COMPOSE="${COMPOSE:-docker compose}"' in src
    # Без тега/коммита — падаем, а не обновляем «что вышло».
    assert re.search(r'\[ -n "\$REF" \] \|\| die', src)
    assert re.search(r'die "нет каталога приложения', src)


def test_deploy_script_waits_for_health_and_version():
    """Выкат считается успешным, только когда контейнер healthy
    и отдаёт ожидаемую версию — а не просто «команда выполнилась»."""
    src = (STATIC_DIR.parent / "deploy" / "deploy.sh").read_text("utf-8")
    assert "State.Health.Status" in src
    assert "HEALTH_TIMEOUT" in src
    assert 'die "не дождались healthy' in src
    # Версию сверяем с /api/health, а не с файлом на диске.
    assert "EXPECT_VERSION" in src
    assert "/api/health" in src


# ---------------- репетиция выката (фаза 1.9) ----------------
#
# Живой сервер и секреты GitHub есть не у всех, а сценарий выката обязан
# быть проверен: иначе deploy.sh «протухает» незаметно и ломается ровно
# в момент релиза. Репетиция (`deploy.sh --dry-run`) гоняет те же проверки
# без Docker, без сети и без SSH — и её гоняет CI на каждый push.


def deploy_script():
    return (STATIC_DIR.parent / "deploy" / "deploy.sh").read_text("utf-8")


def tool(name):
    """Полный путь к утилите: ruff не любит запуск по имени (S607),
    а без bash и git репетицию не потрогать — тогда тест пропускается."""
    import shutil

    import pytest

    found = shutil.which(name)
    if found is None:
        pytest.skip(f"нет {name}")
    return found


def run_rehearsal(ref="HEAD", extra_env=None):
    """Запустить репетицию по-настоящему: нужны только bash и git."""
    import os
    import subprocess

    import pytest

    root = STATIC_DIR.parent
    bash = tool("bash")
    tool("git")
    if not (root / ".git").exists():
        pytest.skip("тесты запущены вне git-репозитория")
    env = {**os.environ, "APP_DIR": str(root), "DRY_RUN": "1", **(extra_env or {})}
    return subprocess.run(  # noqa: S603
        [bash, "deploy/deploy.sh", "--dry-run", ref],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_deploy_script_has_a_rehearsal_mode():
    src = deploy_script()
    assert "--dry-run" in src and 'DRY_RUN="${DRY_RUN:-0}"' in src
    # Репетиция печатает план теми же командами, что исполняет выкат.
    assert 'plan "$COMPOSE up -d --build"' in src
    assert "check_repo" in src
    # Ключ репетиции разбирается до проверки аргументов: порядок не важен.
    assert src.index("--dry-run|-n") < src.index('[ -n "$REF" ] || die')


def test_deploy_rehearsal_passes_without_docker_or_network():
    result = run_rehearsal()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "репетиция" in result.stdout
    assert "up -d --build" in result.stdout, "план выката не напечатан"


def test_deploy_rehearsal_does_not_touch_the_working_tree():
    """Репетиция — не выкат: рабочее дерево и HEAD остаются на месте."""
    import subprocess

    git = tool("git")

    def head():
        return subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=STATIC_DIR.parent,
            capture_output=True,
            text=True,
        ).stdout.strip()

    before = head()
    assert run_rehearsal().returncode == 0
    assert before == head(), "репетиция переключила HEAD"


def test_deploy_rehearsal_refuses_an_unknown_ref():
    result = run_rehearsal("v99.99.99")
    assert result.returncode != 0
    assert "не найден" in result.stderr


def test_deploy_rehearsal_checks_the_version_of_the_tag():
    """Тег обязан указывать на коммит с той же версией в коде: иначе выкат
    «пройдёт», а на сервере окажется другой релиз. Проверяется до сборки.

    Ожидание берём из того же источника, что и скрипт (`git show <ref>`), —
    иначе тест ломался бы на неподкоммиченном бампе версии.
    """
    import subprocess

    git = tool("git")
    declared = subprocess.run(  # noqa: S603
        [git, "show", "HEAD:app/config.py"],
        cwd=STATIC_DIR.parent,
        capture_output=True,
        text=True,
    ).stdout
    version = re.search(r'^APP_VERSION = "([^"]+)"$', declared, re.M)
    assert version, "в HEAD не нашлось APP_VERSION"

    ok = run_rehearsal(extra_env={"EXPECT_VERSION": version.group(1)})
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert f"версия в исходниках: {version.group(1)}" in ok.stdout

    mismatch = run_rehearsal(extra_env={"EXPECT_VERSION": "0.0.1"})
    assert mismatch.returncode != 0
    assert "ожидали «0.0.1»" in mismatch.stderr
    assert "план" not in mismatch.stdout, "на расхождении версий плана нет"


def test_deploy_rehearsal_rejects_a_broken_script():
    """Проверка синтаксиса — часть репетиции: опечатка в deploy-скрипте
    обязана ловиться здесь, а не на сервере посреди выката."""
    assert "bash -n" in deploy_script()
    src = (STATIC_DIR.parent / "deploy" / "backup-cache.sh").read_text("utf-8")
    assert "set -" in src, "скрипты деплоя пишутся под set -e"


def test_deploy_workflow_can_rehearse_without_secrets():
    """До живого сервера workflow проверяется репетицией: тесты релиза,
    секреты (предупреждением, а не падением) и план выката — без SSH."""
    wf, text = deploy_workflow()
    triggers = wf.get("on", wf.get(True))
    assert "dry_run" in triggers["workflow_dispatch"]["inputs"]
    assert "DRY_RUN=1" in text

    steps = wf["jobs"]["deploy"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    rehearsal = next(i for i, r in enumerate(runs) if "DRY_RUN=1" in r)
    ssh = next(i for i, r in enumerate(runs) if "ssh -i" in r)
    assert rehearsal < ssh, "репетиция обязана идти до выката"

    # Ни один SSH-шаг в репетиции не выполняется.
    for step in steps:
        if "ssh " in str(step.get("run", "")):
            assert "dry_run" in str(step.get("if", "")), step.get("name")
    # Секреты в репетиции не обязательны: их отсутствие — предупреждение.
    secrets_step = next(s for s in steps if s.get("name") == "Проверить секреты деплоя")
    assert "warning" in secrets_step["run"] and "exit 0" in secrets_step["run"]


def test_deploy_preflight_matches_ci():
    """Префлайт выката гоняет те же проверки, что и CI: релиз, который
    не прошёл форматирование или рассинхрон словаря, на сервер не едет."""
    steps = deploy_workflow()[0]["jobs"]["deploy"]["steps"]
    preflight = next(str(s["run"]) for s in steps if "pytest" in str(s.get("run", "")))
    for check in ("ruff check", "ruff format --check", "pytest", "node --test"):
        assert check in preflight, f"в префлайте нет {check}"
    assert "build.py --check" in preflight, "релиз не сверяет словарь локализации"


def test_ci_rehearses_the_deploy_script():
    """Сценарий выката гоняется на каждый push — deploy.sh не может
    «протухнуть» незаметно до первого выката."""
    ci = (STATIC_DIR.parent / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    assert "DRY_RUN=1" in ci and "deploy/deploy.sh" in ci
    assert "bash -n" in ci


def test_map_layout_is_shared_and_precached():
    src = read("map-layout.js")
    html = read("index.html")
    assert "module.exports" in src and "root.MapLayout" in src
    assert html.index("/static/map-layout.js") < html.index("/static/leaflet-map.js")
    assert html.index("/static/map-layout.js") < html.index("/static/app.js")
    assert '"/static/map-layout.js"' in read("sw.js")
    for name in ("app.js", "leaflet-map.js"):
        assert "MapLayout.offsets" in read(name)
