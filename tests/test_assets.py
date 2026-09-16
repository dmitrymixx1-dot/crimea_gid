"""Аудит статики (фаза 0.12.0): вес картинок, CSP-совместимая разметка,
согласованность PWA-оболочки. Тесты читают файлы напрямую, сеть не нужна.

Бюджеты веса зеркалят `tools/optimize_images.py`: картинки ужали
ресайзом и качеством, тесты не дают им «растолстеть» обратно.
"""
import json
import re

from app.config import APP_VERSION, STATIC_DIR
from app.services.load import get_attractions

FRONT_FILES = ["index.html", "app.js", "plan-link.js", "catalog-link.js", "sw.js"]

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
