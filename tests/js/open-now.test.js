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

describe("open-now", () => {
  it("крымское время не зависит от пояса устройства", () => {
    // 2026-07-15T06:30Z = 09:30 по Крыму, среда.
    const now = O.crimeaNow(at("2026-07-15T06:30:00Z"));
    assert.equal(now.month, 7);
    assert.equal(now.day, "wed");
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
      "🔴 Закрыто в этом сезоне");
  });

  it("битое правило не притворяется открытым", () => {
    const broken = { schedule: [{ months: "1-12", from: "18:00", to: "09:00" }] };
    const s = O.status(broken, at("2026-07-15T09:00:00Z"));
    assert.equal(s.open, false);
    assert.equal(s.reason, "bad-rule");
  });
});
