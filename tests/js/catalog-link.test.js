// Юнит-тесты фильтров каталога в URL (static/catalog-link.js).
// Запуск: node --test "tests/js/*.test.js" (зависимостей нет, только встроенные модули).
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const L = require("../../static/catalog-link.js");

const F = { tag: "wine", area: "Западный", q: "маяк и вино", sort: "name" };

describe("catalog-link", () => {
  it("дефолты в ссылку не пишутся", () => {
    assert.equal(L.buildCatalogQuery(L.DEFAULTS), "");
    assert.equal(L.buildCatalogQuery({}), "");
    assert.equal(L.buildCatalogQuery({ tag: "beach", sort: "rating" }), "tag=beach");
  });

  it("пишет только tag, area, q, sort и в фиксированном порядке", () => {
    assert.equal(
      L.buildCatalogQuery(F),
      "tag=wine&area=" + encodeURIComponent("Западный") +
        "&q=" + encodeURIComponent("маяк и вино") + "&sort=name",
    );
    assert.equal(
      L.buildCatalogQuery({ sort: "budget", q: "x", area: "a", tag: "t" }),
      "tag=t&area=a&q=x&sort=budget",
    );
  });

  it("round-trip: кириллица, пробелы, &, = и % выживают", () => {
    const weird = { tag: "beach", area: "Южный", q: "мыс & пляж = 100% + ещё", sort: "time" };
    const s = L.buildCatalogQuery(weird);
    assert.deepEqual(L.parseCatalogQuery(s), weird);
    // и после полного цикла через URL (как в браузере: hash -> URLSearchParams)
    const viaUrl = new URLSearchParams(s).toString();
    assert.deepEqual(L.parseCatalogQuery(viaUrl), weird);
  });

  it("parse: мусор не роняет, а даёт дефолты", () => {
    for (const bad of ["", null, undefined, "&&&", "=", "%", "%zz", "tag=", "unknown=1"]) {
      assert.deepEqual(L.parseCatalogQuery(bad), L.DEFAULTS, JSON.stringify(bad));
    }
  });

  it("parse: неизвестная сортировка откатывается на rating", () => {
    assert.equal(L.parseCatalogQuery("sort=turbo").sort, "rating");
    assert.equal(L.parseCatalogQuery("sort=time").sort, "time");
  });

  it("parse: неизвестные ключи игнорируются", () => {
    const out = L.parseCatalogQuery("tag=wine&hack=1&plan=a~b~c");
    assert.deepEqual(out, { ...L.DEFAULTS, tag: "wine" });
  });

  it("catalogUrl: абсолютная ссылка с хэшем и без хвоста при дефолтах", () => {
    assert.equal(
      L.catalogUrl(F, "https://gid.example", "/"),
      "https://gid.example/#/catalog?" + L.buildCatalogQuery(F),
    );
    assert.equal(L.catalogUrl(L.DEFAULTS, "https://gid.example", "/"), "https://gid.example/#/catalog");
  });

  it("KEYS/SORTS — контракт для app.js", () => {
    assert.deepEqual(L.KEYS, ["tag", "area", "q", "sort"]);
    assert.deepEqual(L.SORTS, ["rating", "name", "time", "budget"]);
  });
});
