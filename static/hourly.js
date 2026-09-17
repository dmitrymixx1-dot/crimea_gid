/* Крым.Гид — окно почасового прогноза.
   Чистые функции без DOM: в браузере подключаются как window.Hourly,
   в Node тестируются через node:test.

   Ответ `/api/weather` живёт в кэше до часа, поэтому «сейчас» в нём
   успевает устареть: окно отсчитывает клиент по фактическому часу.
   Час считаем по Крыму (UTC+3) — как в `open-now.js`: турист в Москве
   и в Ялте должен видеть одинаковую строку «сейчас».

   Времена в `hourly[].t` — локальные для города ISO-строки
   («2026-09-17T13:00»). ISO-строки упорядочены как время, поэтому
   сравнение идёт посимвольно, без разбора дат и часовых поясов. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Hourly = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TZ_OFFSET_MIN = 3 * 60;   // Крым — UTC+3, без перехода
  const DEFAULT_COUNT = 12;       // сколько часов показываем в карточке
  const PRECIP_HINT = 30;         // % — ниже этого про дождь не пишем

  /** Ключ часа «сейчас» по Крыму: «2026-09-17T13». */
  function crimeaHour(date) {
    const d = date instanceof Date && !isNaN(date) ? date : new Date();
    const shifted = new Date(d.getTime() + (TZ_OFFSET_MIN + d.getTimezoneOffset()) * 60000);
    const pad = n => String(n).padStart(2, "0");
    return `${shifted.getFullYear()}-${pad(shifted.getMonth() + 1)}-${pad(shifted.getDate())}`
      + `T${pad(shifted.getHours())}`;
  }

  /** Подпись часа: «сейчас» у текущего, иначе «14:00». */
  function hourLabel(iso, nowKey) {
    const t = String(iso);
    return t.slice(0, 13) === nowKey ? "сейчас" : t.slice(11, 16);
  }

  /** Подпись осадков: «💧40%» — только когда дождь действительно вероятен. */
  function precipLabel(value) {
    const n = typeof value === "number" && isFinite(value) ? value : null;
    return n !== null && n >= PRECIP_HINT ? `💧${Math.round(n)}%` : "";
  }

  /**
   * Следующие `count` часов от текущего часа (по Крыму).
   * Прогноз кончился или отстал — возвращаем пустой список: врать
   * про «сейчас» на вчерашних данных хуже, чем промолчать.
   */
  function next(hours, date, count) {
    const limit = Number.isInteger(count) && count > 0 ? count : DEFAULT_COUNT;
    if (!Array.isArray(hours)) return [];
    const items = hours.filter(h => h && typeof h.t === "string" && h.t.length >= 13);
    if (!items.length) return [];

    const nowKey = crimeaHour(date);
    const start = items.findIndex(h => h.t.slice(0, 13) >= nowKey);
    if (start === -1) return [];

    return items.slice(start, start + limit).map(h => ({
      t: h.t,
      label: hourLabel(h.t, nowKey),
      temp: typeof h.temp === "number" ? h.temp : null,
      emoji: typeof h.emoji === "string" ? h.emoji : "",
      precip: typeof h.precip === "number" ? h.precip : null,
      precipLabel: precipLabel(h.precip),
    }));
  }

  return { crimeaHour, hourLabel, precipLabel, next, DEFAULT_COUNT, PRECIP_HINT };
});
