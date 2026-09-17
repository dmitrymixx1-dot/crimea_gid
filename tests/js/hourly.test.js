/* Тесты окна почасового прогноза (static/hourly.js). Без зависимостей:
   node --test, без DOM и сети. */
const test = require("node:test");
const assert = require("node:assert/strict");

const H = require("../../static/hourly.js");

/** Час по Крыму (UTC+3) из UTC-строки. */
const at = iso => new Date(iso);

/** Список часов как в ответе API: локальные ISO-строки города,
    с полудня 17 сентября (Крым = локальное время курорта). */
function hours(count = 30) {
  const out = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(Date.UTC(2026, 8, 17, 12 + i, 0, 0));
    out.push({
      t: d.toISOString().slice(0, 16),
      temp: 20 + (i % 5),
      emoji: "☀️",
      precip: i % 4 === 0 ? 45 : 5,
    });
  }
  return out;
}

test("часовой ключ считается по Крыму, а не по поясу устройства", () => {
  // 2026-09-17T10:20Z = 13:20 по Крыму.
  assert.equal(H.crimeaHour(at("2026-09-17T10:20:00Z")), "2026-09-17T13");
  // Полночь по Крыму — это 21:00 UTC предыдущего дня.
  assert.equal(H.crimeaHour(at("2026-09-16T21:00:00Z")), "2026-09-17T00");
});

test("битая дата не ломает ключ", () => {
  const key = H.crimeaHour("не дата");
  assert.match(key, /^\d{4}-\d{2}-\d{2}T\d{2}$/);
});

test("окно начинается с текущего часа и подписывает его «сейчас»", () => {
  const list = hours();
  // 12:05 по Крыму — час 12:00 уже идёт.
  const out = H.next(list, at("2026-09-17T09:05:00Z"));
  assert.equal(out[0].label, "сейчас");
  assert.equal(out[0].t, "2026-09-17T12:00");
  assert.equal(out[1].label, "13:00");
});

test("окно не перескакивает на следующий час раньше времени", () => {
  const list = hours();
  // 12:59 по Крыму — всё ещё час 12:00.
  const out = H.next(list, at("2026-09-17T09:59:00Z"));
  assert.equal(out[0].t, "2026-09-17T12:00");
  assert.equal(out[0].label, "сейчас");
});

test("по умолчанию показываем 12 часов", () => {
  const list = hours();
  const out = H.next(list, at("2026-09-17T09:05:00Z"));
  assert.equal(out.length, H.DEFAULT_COUNT);
  assert.equal(out.length, 12);
  assert.equal(out.at(-1).t, "2026-09-17T23:00");
});

test("свой размер окна уважается, мусорный — откатывается к дефолту", () => {
  const list = hours();
  assert.equal(H.next(list, at("2026-09-17T09:05:00Z"), 6).length, 6);
  for (const bad of [0, -3, "много", null, 2.5, NaN]) {
    assert.equal(H.next(list, at("2026-09-17T09:05:00Z"), bad).length, 12, String(bad));
  }
});

test("старого прогноза не показываем", () => {
  const list = hours();
  // Ответ из кэша: «сейчас» — вечер 18-го, а последний час в данных — утро.
  const stale = list.slice(0, 5);
  assert.deepEqual(H.next(stale, at("2026-09-18T15:00:00Z")), []);
});

test("прогноз кончился через сутки — пустое окно, а не вчерашние часы", () => {
  const list = hours();
  assert.deepEqual(H.next(list, at("2026-09-19T00:00:00Z")), []);
});

test("день переживается без сдвига: полночь по Крыму", () => {
  const list = [
    { t: "2026-09-16T23:00", temp: 18, emoji: "🌙", precip: 0 },
    { t: "2026-09-17T00:00", temp: 17, emoji: "🌙", precip: 10 },
    { t: "2026-09-17T01:00", temp: 17, emoji: "🌙", precip: 10 },
  ];
  const out = H.next(list, at("2026-09-16T21:30:00Z")); // 00:30 по Крыму 17-го
  assert.equal(out[0].t, "2026-09-17T00:00");
  assert.equal(out[0].label, "сейчас");
  assert.equal(out.length, 2);
});

test("подпись часа отсекает минуты", () => {
  assert.equal(H.hourLabel("2026-09-17T14:00", "2026-09-17T13"), "14:00");
  assert.equal(H.hourLabel("2026-09-17T13:00", "2026-09-17T13"), "сейчас");
  assert.equal(H.hourLabel("2026-09-17T09:00", "2026-09-17T13"), "09:00");
});

test("осадки показываем только от 30%", () => {
  assert.equal(H.precipLabel(45), "💧45%");
  assert.equal(H.precipLabel(30), "💧30%");
  assert.equal(H.precipLabel(29.6), "");
  assert.equal(H.precipLabel(0), "");
  for (const bad of [null, undefined, "40", NaN, Infinity, {}]) {
    assert.equal(H.precipLabel(bad), "", String(bad));
  }
  assert.equal(H.precipLabel(33.4), "💧33%");
});

test("мусорные записи отбрасываются, а не рисуются пустыми", () => {
  const list = [
    { t: "2026-09-17T12:00", temp: 22, emoji: "☀️", precip: 0 },
    null,
    { temp: 30 },                       // без времени
    { t: "12:00", temp: 30 },           // обрезанное время
    { t: "2026-09-17T13:00" },          // без остальных полей
  ];
  const out = H.next(list, at("2026-09-17T09:05:00Z"));
  assert.equal(out.length, 2);
  assert.equal(out[0].label, "сейчас");
  assert.equal(out[1].temp, null);
  assert.equal(out[1].emoji, "");
  assert.equal(out[1].precip, null);
  assert.equal(out[1].precipLabel, "");
});

test("не массив и пустой список — пустое окно", () => {
  for (const bad of [null, undefined, "часы", {}, 42]) {
    assert.deepEqual(H.next(bad, at("2026-09-17T09:05:00Z")), [], String(bad));
  }
  assert.deepEqual(H.next([], at("2026-09-17T09:05:00Z")), []);
});

test("в окне ровно одна подпись «сейчас» — и она первая", () => {
  const list = hours();
  const out = H.next(list, at("2026-09-17T09:05:00Z"));
  assert.equal(out.filter(h => h.label === "сейчас").length, 1);
  assert.equal(out[0].label, "сейчас");
  // Остальные подписи — обычные «ЧЧ:00», без повторов и мусора.
  const labels = out.slice(1).map(h => h.label);
  assert.deepEqual(labels, [...new Set(labels)]);
  assert.ok(labels.every(l => /^\d{2}:\d{2}$/.test(l)), labels.join(","));
});

test("окно идёт по порядку и без пропусков", () => {
  const list = hours();
  const out = H.next(list, at("2026-09-17T09:05:00Z"));
  for (let i = 1; i < out.length; i++) {
    assert.ok(out[i].t > out[i - 1].t, `${out[i - 1].t} → ${out[i].t}`);
  }
});
