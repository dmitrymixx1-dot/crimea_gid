// Юнит-тесты шаринга плана (static/plan-link.js).
// Запуск: node --test "tests/js/*.test.js" (зависимостей нет, только встроенные модули).
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { ORDER, buildPlanString, parsePlanParam } = require("../../static/plan-link.js");

const ANSWERS = {
  purpose: ["beach", "photo"],
  season: "summer",
  tempo: "relax",
  budget: "comfort",
  party: "couple",
  duration: "3-5",
  transport: "car",
};

describe("plan-link", () => {
  it("сериализует ответы в 7 полей через ~", () => {
    assert.equal(
      buildPlanString(ANSWERS),
      "beach,photo~summer~relax~comfort~couple~3-5~car",
    );
  });

  it("round-trip: ссылка переживает encodeURIComponent", () => {
    const s = buildPlanString(ANSWERS);
    const parsed = parsePlanParam(decodeURIComponent(encodeURIComponent(s)));
    assert.deepEqual(parsed, ANSWERS);
  });

  it("порядок полей build и parse совпадает", () => {
    assert.deepEqual(
      ORDER,
      ["purpose", "season", "tempo", "budget", "party", "duration", "transport"],
    );
    assert.equal(buildPlanString(ANSWERS).split("~").length, ORDER.length);
  });

  it("мусор возвращает null, а не исключение", () => {
    for (const bad of ["", "~~~", "a~b~c", "too~many~fields~here~a~b~c~d", null, undefined]) {
      assert.equal(parsePlanParam(bad), null, JSON.stringify(bad));
    }
  });

  it("пустой purpose — null (такая ссылка бесполезна)", () => {
    assert.equal(parsePlanParam("~summer~relax~comfort~couple~3-5~car"), null);
  });

  it("одиночный интерес тоже round-trip", () => {
    const one = { ...ANSWERS, purpose: ["extreme"] };
    assert.deepEqual(parsePlanParam(buildPlanString(one)), one);
  });
});
