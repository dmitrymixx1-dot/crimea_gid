// Юнит-тесты порционного показа каталога (static/catalog-page.js).
// Запуск: node --test "tests/js/*.test.js" (зависимостей нет, только встроенные модули).
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const P = require("../../static/catalog-page.js");

const ITEMS = Array.from({ length: 60 }, (_, i) => ({ id: "p" + i }));

describe("catalog-page", () => {
  it("первая порция не больше страницы и не больше подборки", () => {
    assert.equal(P.firstPage(60), P.PAGE);
    assert.equal(P.firstPage(5), 5);          // короткая подборка целиком
    assert.equal(P.firstPage(0), 0);
    assert.equal(P.firstPage(60, 4), 4);
  });

  it("догрузка растёт шагом и упирается в общее число", () => {
    let shown = P.firstPage(ITEMS.length);
    assert.equal(shown, 12);
    shown = P.growShown(shown, ITEMS.length);
    assert.equal(shown, 24);
    // Докручиваем до конца — переполнения не происходит.
    for (let i = 0; i < 20; i++) shown = P.growShown(shown, ITEMS.length);
    assert.equal(shown, 60);
    assert.equal(P.growShown(60, 60), 60);
  });

  it("visible отдаёт префикс и не мутирует исходный массив", () => {
    const copy = ITEMS.slice();
    const part = P.visible(ITEMS, 12);
    assert.equal(part.length, 12);
    assert.equal(part[0].id, "p0");
    assert.equal(part[11].id, "p11");
    assert.deepEqual(ITEMS, copy);
    // Просят больше, чем есть — отдаём всё, без undefined-дыр.
    assert.equal(P.visible(ITEMS, 999).length, 60);
    assert.ok(P.visible(ITEMS, 999).every(Boolean));
  });

  it("hasMore и remaining честно считают остаток", () => {
    assert.equal(P.remaining(12, 60), 48);
    assert.equal(P.hasMore(12, 60), true);
    assert.equal(P.remaining(60, 60), 0);
    assert.equal(P.hasMore(60, 60), false);
    // Показали больше, чем есть (подборка сузилась фильтром) — не минус.
    assert.equal(P.remaining(99, 60), 0);
    assert.equal(P.hasMore(99, 60), false);
  });

  it("подпись счётчика отражает состояние догрузки", () => {
    assert.equal(P.statusLabel(12, 60), "Показано 12 из 60");
    assert.equal(P.statusLabel(60, 60), "Найдено: 60");
    assert.equal(P.statusLabel(99, 60), "Найдено: 60");
    assert.equal(P.statusLabel(0, 0), "Ничего не найдено");
  });

  it("мусор не роняет расчёты", () => {
    for (const bad of [null, undefined, NaN, -5, "abc", {}]) {
      assert.equal(P.firstPage(bad), 0, String(bad));
      assert.equal(P.remaining(bad, 60), 60, String(bad));
      assert.deepEqual(P.visible(bad, 12), []);
      assert.equal(P.visible(ITEMS, bad).length, 0, String(bad));
    }
    assert.equal(P.growShown(NaN, 60), P.PAGE);
  });

  it("сужение подборки фильтром не оставляет «хвоста»", () => {
    // Показали 36 из 60, затем фильтр оставил 5 — видимая часть = 5.
    assert.equal(P.visible(ITEMS.slice(0, 5), 36).length, 5);
    assert.equal(P.statusLabel(36, 5), "Найдено: 5");
  });
});
