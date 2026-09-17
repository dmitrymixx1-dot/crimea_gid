/* Крым.Гид — «открыто сейчас» по структурированному расписанию.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.OpenNow) и тестируются в Node через node:test.

   Поле `hours` в каталоге — свободный текст и точный источник правды
   для человека. Машинная проверка работает по `schedule`: список правил
   {months, from, to, closed[]}. Точность намеренно до месяца — сезонные
   границы вида «16 июня» огрубляются, поэтому у края сезона возможна
   ошибка в пару дней. Отсюда осторожные формулировки в подписях и
   дисклеймер в интерфейсе: «уточняйте на месте».

   Время считаем по Крыму (UTC+3) независимо от часового пояса
   устройства: турист в Москве и в Екатеринбурге должен видеть
   одинаковый ответ про музей в Ялте. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.OpenNow = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TZ_OFFSET_MIN = 3 * 60;               // Крым — UTC+3, без перехода
  const DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

  /** Момент «сейчас» в крымском времени: {month 1-12, day, minutes}. */
  function crimeaNow(date) {
    const d = date instanceof Date && !isNaN(date) ? date : new Date();
    const shifted = new Date(d.getTime() + (TZ_OFFSET_MIN + d.getTimezoneOffset()) * 60000);
    return {
      month: shifted.getMonth() + 1,
      day: DAYS[shifted.getDay()],
      minutes: shifted.getHours() * 60 + shifted.getMinutes(),
    };
  }

  function toMinutes(hhmm) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || "").trim());
    if (!m) return null;
    const h = Number(m[1]), min = Number(m[2]);
    if (h > 24 || min > 59) return null;
    return h * 60 + min;
  }

  /** Попадает ли месяц в диапазон "4-10" (с переходом через год: "11-3"). */
  function monthInRange(month, range) {
    const m = /^(\d{1,2})-(\d{1,2})$/.exec(String(range || "").trim());
    if (!m) return false;
    const from = Number(m[1]), to = Number(m[2]);
    if (from < 1 || from > 12 || to < 1 || to > 12) return false;
    return from <= to
      ? month >= from && month <= to
      : month >= from || month <= to;     // зимний диапазон
  }

  /** Правило, действующее в этом месяце (первое подходящее). */
  function ruleFor(schedule, month) {
    if (!Array.isArray(schedule)) return null;
    return schedule.find(r => r && monthInRange(month, r.months)) || null;
  }

  /**
   * Статус объекта: { known, open, reason }.
   * known=false — расписания нет, судить не о чем (пляжи, мысы).
   */
  function status(place, date) {
    const schedule = place && place.schedule;
    if (!Array.isArray(schedule) || !schedule.length) {
      return { known: false, open: false, reason: "no-schedule" };
    }
    const now = crimeaNow(date);
    const rule = ruleFor(schedule, now.month);
    if (!rule) return { known: true, open: false, reason: "season" };
    const closed = Array.isArray(rule.closed) ? rule.closed : [];
    if (closed.includes(now.day)) {
      return { known: true, open: false, reason: "day-off" };
    }
    const from = toMinutes(rule.from), to = toMinutes(rule.to);
    if (from === null || to === null || to <= from) {
      return { known: true, open: false, reason: "bad-rule" };
    }
    return now.minutes >= from && now.minutes < to
      ? { known: true, open: true, reason: "open", from: rule.from, to: rule.to }
      : { known: true, open: false, reason: "hours", from: rule.from, to: rule.to };
  }

  /** Короткое «открыто сейчас» — для фильтра. */
  function isOpen(place, date) {
    return status(place, date).open;
  }

  /** Подпись для карточки. Пусто — если сказать нечего. */
  function label(place, date) {
    const s = status(place, date);
    if (!s.known) return "";
    if (s.open) return `🟢 Сейчас открыто · до ${s.to}`;
    if (s.reason === "day-off") return "🔴 Сегодня выходной";
    if (s.reason === "season") return "🔴 Закрыто в этом сезоне";
    if (s.reason === "hours") return `🔴 Сейчас закрыто · c ${s.from}`;
    return "";
  }

  /**
   * Фильтр подборки. Места без расписания НЕ выбрасываем: пляж или мыс
   * открыты всегда, и прятать их по кнопке «открыто сейчас» было бы
   * враньём. Прячем только то, про что точно известно «закрыто».
   */
  function filterOpen(items, date) {
    const list = Array.isArray(items) ? items : [];
    return list.filter(a => {
      const s = status(a, date);
      return !s.known || s.open;
    });
  }

  return {
    TZ_OFFSET_MIN, DAYS, crimeaNow, toMinutes, monthInRange, ruleFor,
    status, isOpen, label, filterOpen,
  };
});
