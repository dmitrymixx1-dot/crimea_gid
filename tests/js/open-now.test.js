// Юнит-тесты «открыто сейчас» (static/open-now.js).
// Запуск: node --test "tests/js/*.test.js" (зависимостей нет, только встроенные модули).
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const O = require("../../static/open-now.js");

// Крымское время = UTC+3. Даты задаём в UTC, чтобы тест не зависел
// от часового пояса машины, где он запущен.
const at = iso => new Date(iso);

const PALACE = {                       // сезонный дворец с зимним окном
  id: "palace",
  schedule: [
    { months: "4-10", from: "09:00", to: "18:00" },
    { months: "11-3", from: "09:00", to: "17:00" },
  ],
};
const MUSEUM = {                       // выходной понедельник
  id: "museum",
  schedule: [{ months: "1-12", from: "10:00", to: "18:00", closed: ["mon"] }],
};
const SUMMER_ONLY = {                  // работает только летом
  id: "summer",
  schedule: [{ months: "6-8", from: "10:00", to: "20:00" }],
};
const BEACH = { id: "beach" };         // расписания нет вовсе
// Дворец с дневными границами: 1–15 июня — до 18:00, 16 июня–15 октября
// — до 19:00, с 16 октября — зимнее окно. Аналог Ливадии в данных.
const PALACE_DAY = {
  id: "palace-day",
  schedule: [
    { months: "5-6", lastDay: 15, from: "10:00", to: "18:00" },
    { months: "6-10", firstDay: 16, lastDay: 15, from: "10:00", to: "19:00" },
    { months: "10-4", firstDay: 16, from: "10:00", to: "17:00" },
  ],
};

describe("open-now", () => {
  it("крымское время не зависит от пояса устройства", () => {
    // 2026-07-15T06:30Z = 09:30 по Крыму, среда, 15-е число.
    const now = O.crimeaNow(at("2026-07-15T06:30:00Z"));
    assert.equal(now.month, 7);
    assert.equal(now.day, "wed");
    assert.equal(now.date, 15);
    assert.equal(now.minutes, 9 * 60 + 30);
  });

  it("месяц попадает в диапазон, в том числе через Новый год", () => {
    assert.equal(O.monthInRange(5, "4-10"), true);
    assert.equal(O.monthInRange(11, "4-10"), false);
    assert.equal(O.monthInRange(12, "11-3"), true);
    assert.equal(O.monthInRange(1, "11-3"), true);
    assert.equal(O.monthInRange(3, "11-3"), true);
    assert.equal(O.monthInRange(4, "11-3"), false);
    for (const bad of ["", null, "abc", "0-5", "4-13", "4"]) {
      assert.equal(O.monthInRange(5, bad), false, String(bad));
    }
  });

  it("разбор времени отсекает мусор", () => {
    assert.equal(O.toMinutes("09:30"), 570);
    assert.equal(O.toMinutes("9:05"), 545);
    for (const bad of ["", null, "25:00", "10:70", "abc", "1000"]) {
      assert.equal(O.toMinutes(bad), null, String(bad));
    }
  });

  it("сезонное правило выбирается по месяцу", () => {
    // Июль, 12:00 — летнее окно, открыто.
    assert.equal(O.isOpen(PALACE, at("2026-07-15T09:00:00Z")), true);
    // Январь, 17:30 по Крыму — зимой закрывается в 17:00.
    assert.equal(O.isOpen(PALACE, at("2026-01-15T14:30:00Z")), false);
    // Июль, 17:30 — летом ещё открыто.
    assert.equal(O.isOpen(PALACE, at("2026-07-15T14:30:00Z")), true);
  });

  it("границы окна: открытие включительно, закрытие — нет", () => {
    assert.equal(O.isOpen(PALACE, at("2026-07-15T06:00:00Z")), true);   // 09:00
    assert.equal(O.isOpen(PALACE, at("2026-07-15T05:59:00Z")), false);  // 08:59
    assert.equal(O.isOpen(PALACE, at("2026-07-15T14:59:00Z")), true);   // 17:59
    assert.equal(O.isOpen(PALACE, at("2026-07-15T15:00:00Z")), false);  // 18:00
  });

  it("выходной день закрывает объект даже в рабочие часы", () => {
    // 2026-07-13 — понедельник, 13:00 по Крыму.
    const mon = O.status(MUSEUM, at("2026-07-13T10:00:00Z"));
    assert.equal(mon.open, false);
    assert.equal(mon.reason, "day-off");
    // Вторник в то же время — открыто.
    assert.equal(O.isOpen(MUSEUM, at("2026-07-14T10:00:00Z")), true);
  });

  it("вне сезона — закрыто с внятной причиной", () => {
    const winter = O.status(SUMMER_ONLY, at("2026-01-15T10:00:00Z"));
    assert.equal(winter.known, true);
    assert.equal(winter.open, false);
    assert.equal(winter.reason, "season");
  });

  it("нет расписания — статус неизвестен, а не «закрыто»", () => {
    const s = O.status(BEACH, at("2026-07-15T02:00:00Z"));
    assert.equal(s.known, false);
    assert.equal(s.reason, "no-schedule");
    assert.equal(O.label(BEACH, at("2026-07-15T02:00:00Z")), "");
    for (const bad of [null, undefined, {}, { schedule: [] }, { schedule: "x" }]) {
      assert.equal(O.status(bad).known, false, JSON.stringify(bad));
    }
  });

  it("фильтр прячет только заведомо закрытое", () => {
    const items = [PALACE, MUSEUM, SUMMER_ONLY, BEACH];
    // Понедельник января, 12:00: дворец открыт, музей — выходной,
    // летний объект вне сезона, пляж без расписания остаётся.
    const open = O.filterOpen(items, at("2026-01-12T09:00:00Z"));
    assert.deepEqual(open.map(a => a.id), ["palace", "beach"]);
    // Ночью закрыто всё, у чего есть расписание.
    const night = O.filterOpen(items, at("2026-07-15T00:00:00Z"));
    assert.deepEqual(night.map(a => a.id), ["beach"]);
    assert.deepEqual(O.filterOpen(null), []);
  });

  it("подписи отражают причину", () => {
    assert.match(O.label(PALACE, at("2026-07-15T09:00:00Z")), /Сейчас открыто/);
    assert.match(O.label(PALACE, at("2026-07-15T18:00:00Z")), /Сейчас закрыто/);
    assert.equal(O.label(MUSEUM, at("2026-07-13T10:00:00Z")), "🔴 Сегодня выходной");
    assert.equal(O.label(SUMMER_ONLY, at("2026-01-15T10:00:00Z")),
      "🔴 Закрыто · открывается в июне");
  });

  it("дневная граница старта сезона: 15-е — старое окно, 16-е — новое", () => {
    // 10 июня, 12:00 по Крыму — окно «май–15 июня», закрытие в 18:00.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-06-10T09:00:00Z")), true);
    // 15 июня, 18:30 — уже за закрытием (18:00) майско-июньского окна.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-06-15T15:30:00Z")), false);
    // 16 июня — летнее окно до 19:00: 18:30 ещё открыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-06-16T15:30:00Z")), true);
  });

  it("окно «до 15 июня» заканчивается в 18:00, а не в 19:00", () => {
    assert.equal(O.isOpen(PALACE_DAY, at("2026-06-15T14:59:00Z")), true);   // 17:59
    assert.equal(O.isOpen(PALACE_DAY, at("2026-06-15T15:00:00Z")), false);  // 18:00 — закрыто
  });

  it("дневная граница конца сезона: 15 октября — лето, 16-е — зима", () => {
    // 15 октября, 18:30 по Крыму — ещё летнее окно (до 19:00).
    assert.equal(O.isOpen(PALACE_DAY, at("2026-10-15T15:30:00Z")), true);
    // 16 октября, 12:00 — зимнее окно (до 17:00): открыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-10-16T09:00:00Z")), true);
    // 16 октября, 17:30 — зимнее окно уже закрыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-10-16T14:30:00Z")), false);
  });

  it("переход на весеннее окно происходит 1 мая, а не «с 16 апреля»", () => {
    // 30 апреля, 12:00 — ещё зимнее окно (до 17:00): открыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-04-30T09:00:00Z")), true);
    // 1 мая — окно «май–15 июня» (до 18:00): 17:30 открыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-05-01T14:30:00Z")), true);
  });

  it("зимнее окно через Новый год уважает firstDay старт-месяца", () => {
    // 20 октября — зимнее окно (firstDay 16): 12:00 открыто.
    assert.equal(O.isOpen(PALACE_DAY, at("2026-10-20T09:00:00Z")), true);
    // 2 февраля — всё ещё зимнее окно: 16:30 открыто (до 17:00).
    assert.equal(O.isOpen(PALACE_DAY, at("2026-02-02T13:30:00Z")), true);
    // 15 апреля — последний день зимнего окна: 16:30 открыто (до 17:00).
    assert.equal(O.isOpen(PALACE_DAY, at("2026-04-15T13:30:00Z")), true);
  });

  it("подпись вне сезона называет дату открытия", () => {
    // Сезон с мая по сентябрь: в ноябре до следующего мая.
    const spring = {
      schedule: [{ months: "5-9", from: "10:00", to: "19:00" }],
    };
    assert.equal(O.label(spring, at("2026-11-20T09:00:00Z")),
      "🔴 Закрыто · открывается в мае");
    // firstDay > 1: окно 6-8 с 16-го июня — в мае дата видна.
    const lateSummer = {
      schedule: [{ months: "6-8", firstDay: 16, from: "10:00", to: "20:00" }],
    };
    assert.equal(O.label(lateSummer, at("2026-05-20T09:00:00Z")),
      "🔴 Закрыто · открывается 16 июня");
  });

  it("нечитаемые дневные границы деградируют до месячных", () => {
    const sloppy = {
      schedule: [{ months: "6-8", firstDay: 99, lastDay: 0, from: "10:00", to: "20:00" }],
    };
    // firstDay 99 / lastDay 0 — мусор: окно месяца целиком, без падения.
    assert.equal(O.isOpen(sloppy, at("2026-07-01T09:00:00Z")), true);
    assert.equal(O.isOpen(sloppy, at("2026-07-31T16:00:00Z")), true);
    const badText = {
      schedule: [{ months: "6-8", firstDay: "x", from: "10:00", to: "20:00" }],
    };
    assert.equal(O.isOpen(badText, at("2026-06-10T09:00:00Z")), true);
  });

  it("ruleFor выбирает правило по числу, не только по месяцу", () => {
    const sched = PALACE_DAY.schedule;
    assert.equal(O.ruleFor(sched, 6, 10).to, "18:00");
    assert.equal(O.ruleFor(sched, 6, 16).to, "19:00");
    assert.equal(O.ruleFor(sched, 10, 15).to, "19:00");
    assert.equal(O.ruleFor(sched, 10, 16).to, "17:00");
  });

  it("битое правило не притворяется открытым", () => {
    const broken = { schedule: [{ months: "1-12", from: "18:00", to: "09:00" }] };
    const s = O.status(broken, at("2026-07-15T09:00:00Z"));
    assert.equal(s.open, false);
    assert.equal(s.reason, "bad-rule");
  });
});
