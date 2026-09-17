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

/* Заголовки ответа: у каждой ручки свой бюджет, поэтому имя правила
   в бюджете так же важно, как числа. */
function headers(map) {
  return { get: name => (name in map ? map[name] : null) };
}

describe("readBudget", () => {
  it("читает бюджет и имя правила", () => {
    const budget = R.readBudget(
      headers({
        "X-RateLimit-Rule": "news",
        "X-RateLimit-Limit": "6",
        "X-RateLimit-Remaining": "4",
        "X-RateLimit-Reset": "300",
      })
    );
    assert.deepEqual(budget, {
      rule: "news",
      limit: 6,
      remaining: 4,
      reset: 300,
    });
  });

  it("нет заголовков — null, а не выдуманный лимит", () => {
    assert.equal(R.readBudget(headers({})), null);
    assert.equal(R.readBudget(null), null);
    assert.equal(R.readBudget({}), null, "не Headers и не объект с get");
  });

  it("мусор в числах → null в поле, а не NaN", () => {
    const budget = R.readBudget(
      headers({ "X-RateLimit-Limit": "шесть", "X-RateLimit-Remaining": "0" })
    );
    assert.deepEqual(budget, { rule: null, limit: null, remaining: 0, reset: null });
  });

  it("пустое имя правила не превращается в строку «null»", () => {
    const budget = R.readBudget(headers({ "X-RateLimit-Remaining": "1" }));
    assert.equal(budget.rule, null);
  });
});

describe("cooldownSeconds", () => {
  it("пустой бюджет — ждать нечего", () => {
    assert.equal(R.cooldownSeconds(null), 0);
    assert.equal(R.cooldownSeconds({ remaining: 3, reset: 300 }), 0);
  });

  it("исчерпанный бюджет держит кнопку до открытия окна", () => {
    assert.equal(R.cooldownSeconds({ remaining: 0, reset: 300 }), 300);
    assert.equal(R.cooldownSeconds({ remaining: 0, reset: null }), 0);
    assert.equal(R.cooldownSeconds({ remaining: 0, reset: "хз" }), 0);
  });

  it("прямой отказ важнее пустого бюджета: берём большее из двух", () => {
    assert.equal(R.cooldownSeconds(null, "30"), 30);
    assert.equal(R.cooldownSeconds({ remaining: 0, reset: 60 }, "30"), 60);
    assert.equal(R.cooldownSeconds({ remaining: 0, reset: 10 }, "45"), 45);
  });

  it("не обещает отдых дольше часа", () => {
    assert.equal(R.cooldownSeconds(null, "99999"), R.MAX_SECONDS);
  });
});

describe("budgetText", () => {
  it("показывает остаток словами", () => {
    assert.equal(
      R.budgetText({ limit: 6, remaining: 1 }),
      "осталось 1 обновление из 6"
    );
    assert.equal(
      R.budgetText({ limit: 6, remaining: 2 }),
      "осталось 2 обновления из 6"
    );
    assert.equal(
      R.budgetText({ limit: 6, remaining: 5 }),
      "осталось 5 обновлений из 6"
    );
  });

  it("исчерпанный бюджет — не «осталось 0», а факт", () => {
    assert.equal(R.budgetText({ limit: 6, remaining: 0 }), "обновления исчерпаны");
  });

  it("полный и незнакомый бюджет молчат", () => {
    assert.equal(R.budgetText({ limit: 6, remaining: 6 }), "");
    assert.equal(R.budgetText({ limit: null, remaining: 3 }), "");
    assert.equal(R.budgetText({ limit: 6, remaining: null }), "");
    assert.equal(R.budgetText(null), "");
  });
});
