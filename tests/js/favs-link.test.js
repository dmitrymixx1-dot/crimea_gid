// Юнит-тесты шаринга избранного (static/favs-link.js).
// Запуск: node --test "tests/js/*.test.js" (зависимостей нет).
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const F = require("../../static/favs-link.js");

const KNOWN = ["lastochino", "vorontsov", "sudak", "krym-miniature"];

describe("favs-link", () => {
  it("собирает query из id, убивая дубли и мусор", () => {
    assert.equal(F.buildFavsQuery(["a", "b", "a", "c"]), "f=a,b,c");
    // Чужие форматы slug, пустые и не-строки отбрасываются.
    assert.equal(F.buildFavsQuery(["a", "", " ", "A", "b c", "x-y", 42, null]),
      "f=a,x-y");
    assert.equal(F.buildFavsQuery([]), "");
    assert.equal(F.buildFavsQuery("nope"), "");
  });

  it("round-trip: query → те же id, порядок сохраняется", () => {
    const ids = ["sudak", "krym-miniature", "lastochino"];
    const parsed = F.parseFavsQuery(F.buildFavsQuery(ids), KNOWN);
    assert.deepEqual(parsed, ids);
  });

  it("признаёт только id, которые есть в каталоге получателя", () => {
    const q = F.buildFavsQuery(["lastochino", "ghost-place", "b c"]);
    assert.deepEqual(F.parseFavsQuery(q, KNOWN), ["lastochino"]);
    // id каталога, которого нет у отправителя, тоже не появляется.
    assert.deepEqual(F.parseFavsQuery("f=sudak", []), []);
  });

  it("устойчив к мусору в query", () => {
    assert.deepEqual(F.parseFavsQuery("", KNOWN), []);
    assert.deepEqual(F.parseFavsQuery(null, KNOWN), []);
    // То же контрактное чтение query, что у catalog-link: ведущий
    // «?» или «#» допускаются, путь — нет.
    assert.deepEqual(F.parseFavsQuery("#f=lastochino", KNOWN),
      ["lastochino"]);
    assert.deepEqual(F.parseFavsQuery("?f=lastochino", KNOWN),
      ["lastochino"]);
    // Иные параметры игнорируются.
    assert.deepEqual(F.parseFavsQuery("tag=beach&f=sudak", KNOWN), ["sudak"]);
    // Дубли в query схлопываются.
    assert.deepEqual(F.parseFavsQuery("f=sudak,sudak,sudak", KNOWN), ["sudak"]);
    // Битый percent-encoding не роняет парсер.
    assert.deepEqual(F.parseFavsQuery("f=%E2%288%85", KNOWN), []);
    // Пустые элементы списка — не id.
    assert.deepEqual(F.parseFavsQuery("f=,sudak,,", KNOWN), ["sudak"]);
  });

  it("favsUrl складывает полный URL; пустое избранное — пустая строка", () => {
    assert.equal(F.favsUrl(["a", "b"], "https://gid.example", "/"),
      "https://gid.example/#/favs?f=a,b");
    assert.equal(F.favsUrl([], "https://gid.example", "/"), "");
    // Без origin — относительный URL (шаринг на том же сайте).
    assert.equal(F.favsUrl(["a"], "", "/"), "/#/favs?f=a");
  });

  it("порядок id берётся из query, а не из каталога", () => {
    const parsed = F.parseFavsQuery("f=krym-miniature,lastochino", KNOWN);
    assert.deepEqual(parsed, ["krym-miniature", "lastochino"]);
  });

  it("чистит id тем же правилами, что и сборка ссылки", () => {
    // пробелы обрезаются, дубли схлопываются, чужие форматы отбрасываются
    assert.deepEqual(F.cleanIds([" a ", "a", "B", "x y", "a-b_c", "z9-x"]),
      ["a", "z9-x"]);
  });
});
