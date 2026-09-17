"""Опциональная проверка настоящего UI, отдельно от бессетевого pytest.

Запустить приложение, затем:
  pip install -r requirements-browser.txt
  playwright install chromium
  python tools/browser_smoke.py

BROWSER_URL — адрес уже запущенного приложения (по умолчанию localhost:8000).
CHROMIUM_PATH — необязательный путь к системному Chromium.
Внешние тайлы подменены: тест проверяет Leaflet, не доступность OSM.
"""

# ruff: noqa: S101 -- опциональный тест, assert здесь намеренный

import base64
import os

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BROWSER_URL", "http://localhost:8000").rstrip("/")
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
ANSWERS = ["summer", "relax", "comfort", "couple", "3-5", "car"]


def navigate(page, target):
    link = page.locator(f'.nav a[data-nav="{target}"]')
    if not link.is_visible():
        page.locator("#nav-toggle").click()
    link.click()


def check(browser, width):
    context = browser.new_context(
        viewport={"width": width, "height": 844},
        locale="ru-RU",
        permissions=["clipboard-read", "clipboard-write"],
    )
    context.route(
        "https://tile.openstreetmap.org/**",
        lambda route: route.fulfill(content_type="image/png", body=PNG),
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(error.stack))
    page.goto(BASE + "/#/quiz")
    expect(page.locator(".quiz-step")).to_have_text("1 / 7")
    page.locator("[data-opt=beach]").click()
    page.locator("#q-next").click()
    expect(page.locator(".quiz-step")).to_have_text("2 / 7")
    # Назад сохраняет первый ответ, не отправляет неполную анкету.
    page.locator("#q-back").click()
    expect(page.locator("[data-opt=beach]")).to_have_class("option selected")
    page.locator("#q-next").click()
    for step, answer in enumerate(ANSWERS, 2):
        expect(page.locator(".quiz-step")).to_have_text(f"{step} / 7")
        page.locator(f'[data-opt="{answer}"]').click()
    with page.expect_request("**/api/quiz/evaluate") as request:
        page.locator("#q-next").click()
    assert request.value.post_data_json == dict(
        zip(
            ["purpose", "season", "tempo", "budget", "party", "duration", "transport"],
            [["beach"], *ANSWERS],
            strict=True,
        )
    )
    expect(page.locator(".day-card")).to_have_count(4)
    stops = page.locator(".stop").evaluate_all("els => els.map(e => e.dataset.id)")
    page.locator("#plan-copy").click()
    plan_url = page.evaluate("navigator.clipboard.readText()")
    assert "#/quiz?plan=" in plan_url
    # Новый браузерный контекст: никакого прежнего state/localStorage.
    recipient = browser.new_context(locale="ru-RU")
    other = recipient.new_page()
    other.goto(plan_url)
    expect(other.locator(".day-card")).to_have_count(4)
    assert (
        other.locator(".stop").evaluate_all("els => els.map(e => e.dataset.id)")
        == stops
    )
    recipient.close()

    navigate(page, "map")
    page.locator("#map-plan").click()
    expect(page.locator("#plan-layer g")).to_have_count(len(stops))
    page.locator('[data-layer="leaflet"]').click()
    expect(page.locator(".lm-plan-num")).to_have_count(len(stops))
    page.locator("#map-plan").click()
    expect(page.locator(".lm-plan-num")).to_have_count(0)
    page.locator('[data-layer="svg"]').click()
    navigate(page, "catalog")
    page.locator("#cat-search").fill("Коктебель")
    cards = page.locator("#cat-grid .card")
    expect(cards).to_have_count(2)
    ids = cards.evaluate_all("els => els.map(e => e.dataset.id)")
    fav = page.locator(f'[data-fav="{ids[0]}"]')
    fav.click()
    expect(fav).to_have_class("fav-btn on")
    page.locator("#cat-share").click()
    catalog_url = page.evaluate("navigator.clipboard.readText()")
    page.goto(catalog_url)
    expect(page.locator("#cat-grid .card")).to_have_count(2)
    expect(page.locator(f'[data-fav="{ids[0]}"]')).to_have_class("fav-btn on")
    page.locator("#cat-grid .card").first.click()
    expect(page.locator(".modal")).to_be_visible()
    page.locator("#m-share").click()
    place_url = page.evaluate("navigator.clipboard.readText()")
    page.keyboard.press("Escape")
    page.goto(place_url)
    expect(page.locator(".modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".modal")).to_have_count(0)

    navigate(page, "map")
    for id_ in ids:
        marker = page.locator(f'.marker[data-id="{id_}"]')
        marker.click()  # Без force: браузер проверяет, не накрыт ли маркер.
        expect(page.locator(".modal")).to_be_visible()
        page.keyboard.press("Escape")
        marker.focus()
        page.keyboard.press("Enter")
        expect(page.locator(".modal")).to_be_visible()
        page.keyboard.press("Escape")
        expect(marker).to_be_focused()
    page.locator('[data-layer="leaflet"]').click()
    expect(page.locator(".lm-marker")).to_have_count(60)
    expect(page.locator("#lm-interactive")).to_be_visible()
    for id_ in ids:
        name = page.evaluate("id => state.attractions.find(a => a.id === id).name", id_)
        page.locator(".lm-marker").and_(page.get_by_title(name, exact=True)).click()
        expect(page.locator(".modal")).to_be_visible()
        page.keyboard.press("Escape")
    for _ in range(2):
        page.locator(".leaflet-control-zoom-in").click()
    positions = page.evaluate(
        """ids => document.querySelector('#lm-interactive')._lm.markers
          .getLayers().filter(m => m.options && ids.includes(m.options.title))
          .map(m => m.getElement().getBoundingClientRect().x)""",
        [
            page.evaluate("id => state.attractions.find(a => a.id === id).name", i)
            for i in ids
        ],
    )
    assert len(positions) == 2 and abs(positions[0] - positions[1]) >= 40
    page.locator('#map-tags [data-tag="wine"]').click()
    expect(page.locator("#lm-interactive")).to_be_visible()
    expect(page.locator(".lm-marker")).not_to_have_count(60)
    page.locator('#map-tags [data-tag="wine"]').click()
    expect(page.locator(".lm-marker")).to_have_count(60)
    page.locator('[data-layer="svg"]').click()
    page.locator("#lang-toggle").click()
    expect(page.locator("#view h2")).to_contain_text("Map of Crimea")
    page.locator("#lang-toggle").click()
    expect(page.locator("#view h2")).to_contain_text("Карта Крыма")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
        "горизонтальный скролл"
    )

    # Дождаться SW, затем загрузить API уже под его контролем.
    page.evaluate("navigator.serviceWorker.ready")
    page.reload()
    expect(page.locator(".marker")).to_have_count(60)
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    page.wait_for_function(
        """async () => !!(await caches.match('/api/attractions'))
          && !!(await caches.match('/api/quiz'))
          && !!(await caches.match('/api/areas'))
          && !!(await caches.match('/api/tags'))"""
    )
    context.set_offline(True)
    page.reload()
    expect(page.locator(".marker")).to_have_count(60)
    assert not errors, errors
    context.close()
    print(
        f"PASS {width}px: 7 вопросов, шаринг, каталог, избранное, модалки, "
        "обе карты, зум, фильтры, RU/EN, офлайн"
    )


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH") or None,
            args=[
                "--disable-dev-shm-usage",
                "--use-gl=angle",
                "--use-angle=swiftshader",
            ],
        )
        try:
            for width in (1280, 390):
                check(browser, width)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
