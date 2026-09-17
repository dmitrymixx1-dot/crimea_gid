/* Тесты ответа на 429 (static/rate-limit.js). Без зависимостей:
   node --test, без DOM и сети. */
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const R = require("../../static/rate-limit.js");

describe("parseRetryAfter", () => {
  it("читает секунды из заголовка", () => {
    assert.equal(R.parseRetryAfter("30"), 30);
    assert.equal(R.parseRetryAfter(" 5 "), 5);
    assert.equal(R.parseRetryAfter(0), 0);
  });

  it("мусор и пустота → null, а не NaN и не ноль", () => {
    for (const v of ["", "  ", null, undefined, "soon", "abc", NaN, Infinity]) {
      assert.equal(R.parseRetryAfter(v), null, String(v));
    }
    // Отрицательное время сервер прислать не мог — не верим.
    assert.equal(R.parseRetryAfter("-5"), null);
  });

  it("не обещает ждать дольше часа", () => {
    assert.equal(R.parseRetryAfter("7200"), R.MAX_SECONDS);
    assert.equal(R.parseRetryAfter("3600"), 3600);
  });

  it("секунды округляются, а не обрубаются", () => {
    assert.equal(R.parseRetryAfter("4.6"), 5);
  });
});

describe("plural", () => {
  it("склоняет минуты по-русски", () => {
    const forms = ["минуту", "минуты", "минут"];
    assert.equal(R.plural(1, forms), "минуту");
    assert.equal(R.plural(2, forms), "минуты");
    assert.equal(R.plural(4, forms), "минуты");
    assert.equal(R.plural(5, forms), "минут");
    assert.equal(R.plural(11, forms), "минут");
    assert.equal(R.plural(21, forms), "минуту");
    assert.equal(R.plural(22, forms), "минуты");
    assert.equal(R.plural(111, forms), "минут");
  });
});

describe("waitText", () => {
  it("меньше минуты — секунды", () => {
    assert.equal(R.waitText(1), "через 1 с");
    assert.equal(R.waitText(45), "через 45 с");
  });

  it("от минуты — минуты с округлением вверх", () => {
    assert.equal(R.waitText(60), "через 1 минуту");
    assert.equal(R.waitText(61), "через 2 минуты");
    assert.equal(R.waitText(120), "через 2 минуты");
    assert.equal(R.waitText(300), "через 5 минут");
    assert.equal(R.waitText("301"), "через 6 минут");
  });

  it("нет данных — пустая строка, а не «через undefined»", () => {
    assert.equal(R.waitText(null), "");
    assert.equal(R.waitText(undefined), "");
    assert.equal(R.waitText(0), "");
    assert.equal(R.waitText("nope"), "");
  });
});

describe("message", () => {
  it("показывает время ожидания, если сервер его прислал", () => {
    assert.equal(R.message("30"), "Слишком часто. Попробуйте через 30 с.");
    assert.equal(R.message(300), "Слишком часто. Попробуйте через 5 минут.");
  });

  it("без Retry-After не выдумывает время", () => {
    assert.equal(R.message(null), "Слишком часто. Попробуйте позже.");
    assert.equal(R.message(undefined), "Слишком часто. Попробуйте позже.");
    assert.equal(R.message("хз"), "Слишком часто. Попробуйте позже.");
  });
});
