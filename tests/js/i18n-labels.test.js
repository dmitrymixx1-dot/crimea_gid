// Покрытие английской локалью подписей, которые СОБИРАЮТ модули фронта.
// Статический `tools/i18n_extract.py` их не видит: строка появляется только
// в момент вызова (`Найдено: 12`, `через 3 минуты`), поэтому её проверяет
// тест — вызывает функцию и требует, чтобы словарь знал результат.
// Запуск: node --test "tests/js/*.test.js"
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const I = require("../../static/i18n.js");
const OpenNow = require("../../static/open-now.js");
const CatalogPage = require("../../static/catalog-page.js");
const RateLimit = require("../../static/rate-limit.js");
const Hourly = require("../../static/hourly.js");

const BUNDLE = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../../static/i18n/en.json"), "utf8")
);

/**
 * Русская фраза обязана иметь английский перевод, и перевод обязан
 * отличаться от оригинала: словарь может содержать и саму себя (значения
 * заполняет `tools/i18n_en/build.py`, дыра выглядела бы как перевод).
 */
function expectEnglish(ru, note) {
  assert.ok(I.has(ru), `нет ключа в словаре: ${JSON.stringify(ru)} (${note})`);
  const en = I.translate(ru);
  assert.notEqual(en, ru, `перевод совпал с оригиналом: ${JSON.stringify(ru)} (${note})`);
  const cyrill = /[а-яё]/.exec(en);
  assert.ok(
    !cyrill || en.includes("Крым.Гид"),
    `в английском тексте кириллица ${JSON.stringify(cyrill && cyrill[0])}: ${en}`
  );
  return en;
}

describe("labels: словарь покрывает подписи модулей", () => {
  it("бандл на месте и английский включён", () => {
    I.setLang("en", BUNDLE);
    assert.equal(I.lang(), "en");
    assert.ok(Object.keys(I.dictFrom(BUNDLE)).length > 300, "словарь подозрительно мал");
  });

  it("на русском словари не касаются: строки остаются оригиналами", () => {
    I.setLang("ru");
    assert.equal(I.translate("Найдено: 12"), "Найдено: 12");
    assert.equal(I.has("Найдено: 12"), false);
    I.setLang("en", BUNDLE);
  });

  describe("CatalogPage.statusLabel", () => {
    const cases = [
      [0, 0], [12, 60], [24, 60], [60, 60], [5, 5], [3, 3],
    ];
    it("порции и счётчик каталога", () => {
      for (const [shown, total] of cases) {
        const ru = CatalogPage.statusLabel(shown, total);
        expectEnglish(ru, `shown=${shown}, total=${total}`);
      }
      assert.equal(
        I.translate(CatalogPage.statusLabel(24, 60)),
        "Showing 24 of 60",
        "числа должны доехать до перевода"
      );
    });

    it("пустая выборка — «ничего не найдено», а не «найдено: 0»", () => {
      expectEnglish(CatalogPage.statusLabel(0, 0), "empty");
      expectEnglish(CatalogPage.statusLabel(12, null), "no total");
    });
  });

  describe("RateLimit: ожидание и бюджет", () => {
    it("секунды и минуты с русской формой числа", () => {
      for (const s of [1, 5, 30, 59, 60, 61, 90, 120, 300, 1000]) {
        expectEnglish(RateLimit.waitText(s), `wait ${s}`);
      }
      assert.equal(RateLimit.waitText(0), "", "нулевое ожидание — пустая строка");
      expectEnglish(RateLimit.message(null), "без Retry-After");
      for (const s of [5, 60, 90, 300]) {
        expectEnglish(RateLimit.message(s), `message ${s}`);
      }
    });

    it("остаток бюджета ленты", () => {
      const cases = [
        { remaining: 0, limit: 5 }, { remaining: 1, limit: 5 },
        { remaining: 2, limit: 5 }, { remaining: 5, limit: 7 },
        { remaining: 11, limit: 20 }, { remaining: 21, limit: 25 },
      ];
      for (const budget of cases) {
        expectEnglish(RateLimit.budgetText(budget), `budget ${JSON.stringify(budget)}`);
      }
      assert.equal(RateLimit.budgetText(null), "", "без бюджета — молчим");
      expectEnglish(RateLimit.budgetText({ remaining: 0, limit: 5 }), "исчерпано");
    });
  });

  describe("OpenNow.label: «открыто сейчас»", () => {
    const summer = [{ months: "5-10", from: "10:00", to: "19:00" }];
    it("открыто, закрыто на час, выходной день", () => {
      const open = OpenNow.label({ schedule: summer }, new Date("2026-06-15T10:00:00Z"));
      expectEnglish(open, "open");
      assert.equal(I.translate(open), "🟢 Open now · until 19:00");

      const early = OpenNow.label({ schedule: summer }, new Date("2026-06-15T05:00:00Z"));
      expectEnglish(early, "before opening");
      const monday = OpenNow.label(
        { schedule: [{ ...summer[0], closed: ["mon"] }] },
        new Date("2026-06-15T10:00:00Z")   // 15 июня 2026-го — понедельник
      );
      expectEnglish(monday, "day off");
      assert.equal(OpenNow.label({ schedule: [] }, new Date()), "",
        "без расписания модуль молчит — и переводить нечего");
    });

    it("сезон закрыт: «открывается …» во всех формах", () => {
      // «15 мая» (день больше первого) и «в апреле» (первое число) — две
      // разные подписи `formatOpens`, обе обязаны быть в словаре.
      const late = OpenNow.label(
        { schedule: [{ months: "5-9", firstDay: 15, from: "10:00", to: "19:00" }] },
        new Date("2026-02-10T10:00:00Z")
      );
      expectEnglish(late, "opens on the 15th");
      assert.match(late, /^🔴 Закрыто · открывается 15 мая$/);
      const first = OpenNow.label(
        { schedule: [{ months: "4-9", from: "10:00", to: "19:00" }] },
        new Date("2026-02-10T10:00:00Z")
      );
      expectEnglish(first, "opens on the 1st");
      assert.match(first, /^🔴 Закрыто · открывается в апреле$/);
      // Все месяцы: `MONTHS_*` модуля — те же подписи, что видит человек.
      for (let m = 0; m < 12; m++) {
        expectEnglish(`🔴 Закрыто · открывается в ${OpenNow.MONTHS_LOC[m]}`, `loc ${m}`);
        expectEnglish(`🔴 Закрыто · открывается 7 ${OpenNow.MONTHS_GEN[m]}`, `gen ${m}`);
      }
      expectEnglish("🔴 Закрыто в этом сезоне", "no next window");
      // Месяцы правила не читались: сказать нечего, и модуль отдаёт «сезон»
      // без даты — именно эта ветка обязана быть переведена.
      const blind = OpenNow.label({ schedule: [{ months: "когда-нибудь" }] }, new Date());
      assert.equal(blind, "🔴 Закрыто в этом сезоне");
    });
  });

  describe("Hourly и карта", () => {
    it("«сейчас» в почасовом окне", () => {
      expectEnglish(Hourly.hourLabel("2026-09-17T13:00", "2026-09-17T13"), "now");
      assert.equal(Hourly.hourLabel("2026-09-17T15:00", "2026-09-17T13"), "15:00",
        "час — не подпись, переводить нечего");
    });

    it("авария карты: наружу идёт подпись app.js, а не текст модуля", () => {
      // `LeafletMap` бросает русскую ошибку, но её видно только в консоли:
      // человеку app.js показывает свою фразу — её требует
      // tools/i18n_extract.py, и словарю не надо дублировать чужой текст.
      const mod = fs.readFileSync(path.join(__dirname, "../../static/leaflet-map.js"), "utf8");
      const app = fs.readFileSync(path.join(__dirname, "../../static/app.js"), "utf8");
      assert.match(mod, /new Error\("[^"]*[а-яё][^"]*"\)/, "модуль обязан падать по-человечески");
      assert.match(app, /console\.warn\("Leaflet failed:", err\)/);
      expectEnglish("Не удалось загрузить интерактивную карту — остаёмся на схеме",
        "map fallback");
    });
  });

  it("кастомные подписи квиза и планов тоже в словаре", () => {
    // Эти фразы собираются не модулями, а данными (`app/data/quiz.json`) и
    // Python-подписями; здесь — контроль того, что фронт подставляет их
    // именно в таком виде (числа свёрнуты, падежные формы разделены).
    for (const ru of [
      "Вам подобрали {n}",
      "на {days} дн., из {all} подходящих",
      "Показать ещё {step} из {left}",
      "обновлено {time}{failed}",
      "кэш от {time}",
    ]) {
      assert.ok(I.has(ru), `нет ключа-шаблона: ${ru}`);
    }
  });
});
