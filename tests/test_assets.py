"""Аудит статики (фаза 0.12.0): вес картинок, CSP-совместимая разметка,
согласованность PWA-оболочки. Тесты читают файлы напрямую, сеть не нужна.

Бюджеты веса зеркалят `tools/optimize_images.py`: картинки ужали
ресайзом и качеством, тесты не дают им «растолстеть» обратно.
"""
import json
import re

from app.config import APP_VERSION, STATIC_DIR
from app.services.load import get_attractions

FRONT_FILES = ["index.html", "app.js", "plan-link.js", "catalog-link.js",
               "favs-link.js", "sw.js"]

BUDGET_HERO = 220_000     # байт
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
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
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
        assert re.search(r'alt="[^"]+"', tag), tag   # непустой alt у каждой
    assert 'alt=""' not in app
    assert 'alt=""' not in read("index.html")


def test_no_javascript_urls():
    for name in FRONT_FILES:
        assert "javascript:" not in read(name).lower(), name


# ---------------- согласованность оболочки ----------------

def test_manifest_mentions_real_catalog_size():
    m = json.loads(read("manifest.webmanifest"))
    assert str(len(get_attractions())) in m["description"], m["description"]


def test_index_connects_catalog_link_module():
    html = read("index.html")
    assert 'src="/static/catalog-link.js"' in html
    assert 'src="/static/plan-link.js"' in html


def test_sw_shell_covers_umd_modules():
    sw = read("sw.js")
    assert '"/static/catalog-link.js"' in sw
    assert '"/static/plan-link.js"' in sw
    # сырой index.html с плейсхолдером __ORIGIN__ в precache не нужен:
    # оболочка кеширует отрендеренный ответ GET /
    assert '"/static/index.html"' not in sw
    assert f"crimea-gid-v{APP_VERSION}" in sw


def test_catalog_link_module_is_umd():
    src = read("catalog-link.js")
    assert "module.exports" in src and "root.CatalogLink" in src


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
    assert "/api/health" in caddy          # проверка живости бэкенда
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
