/* Крым.Гид — «открыто сейчас» по структурированному расписанию.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.OpenNow) и тестируются в Node через node:test.

   Поле `hours` в каталоге — свободный текст и точный источник правды
   для человека. Машинная проверка работает по `schedule`: список правил
   {months, from, to, closed[], firstDay?, lastDay?}. Точность — до дня:
   `firstDay` сдвигает старт окна в стартовом месяце диапазона, `lastDay`
   — его конец в завершающем («16 июня» = firstDay 16 у правила 6-…;
   «15 октября» = lastDay 15 у правила …-10). То, что выразить нельзя
   (санитарные дни, закрытия на непогоду), остаётся в тексте `hours` —
   отсюда дисклеймер «уточняйте на месте» в интерфейсе.

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
  // Genitiv для дат («16 июня»), locativ для «в июне».
  const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const MONTHS_LOC = ["январе", "феврале", "марте", "апреле", "мае", "июне",
    "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"];

  /** Момент «сейчас» в крымском времени: {month 1-12, day, date, minutes}. */
  function crimeaNow(date) {
    const d = date instanceof Date && !isNaN(date) ? date : new Date();
    const shifted = new Date(d.getTime() + (TZ_OFFSET_MIN + d.getTimezoneOffset()) * 60000);
    return {
      month: shifted.getMonth() + 1,
      day: DAYS[shifted.getDay()],
      date: shifted.getDate(),
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

  function dayBound(value, fallback) {
    const n = Number(value);
    return Number.isInteger(n) && n >= 1 && n <= 31 ? n : fallback;
  }

  /**
   * Попадает ли (месяц, число) в календарное окно правила.
   * `firstDay` срезает начало старт-месяца, `lastDay` — конец
   * завершающего; зимние диапазоны "11-3" — это 11-12 и 1-3.
   * Нечитаемые границы деградируют до месячных (окно месяца целиком).
   */
  function dayInWindow(month, date, range, firstDay, lastDay) {
    if (!monthInRange(month, range)) return false;
    const m = /^(\d{1,2})-(\d{1,2})$/.exec(String(range || "").trim());
    const start = Number(m[1]), end = Number(m[2]);
    if (month === start && date < dayBound(firstDay, 1)) return false;
    const last = lastDay === undefined || lastDay === null
      ? 31 : dayBound(lastDay, 31);
    if (month === end && date > last) return false;
    return true;
  }

  /** Правило, действующее в эту дату (первое подходящее). */
  function ruleFor(schedule, month, date) {
    if (!Array.isArray(schedule)) return null;
    return schedule.find(r => r && dayInWindow(month, date, r.months, r.firstDay, r.lastDay)) || null;
  }

  /** Старт окна правила: {month, day} — старт-месяц и firstDay. */
  function windowStart(rule) {
    const m = /^(\d{1,2})-(\d{1,2})$/.exec(String((rule && rule.months) || "").trim());
    if (!m) return null;
    const start = Number(m[1]);
    if (start < 1 || start > 12) return null;
    return { month: start, day: dayBound(rule.firstDay, 1) };
  }

  function formatOpens(ws) {
    if (!ws) return "";
    return ws.day > 1
      ? ws.day + " " + MONTHS_GEN[ws.month - 1]
      : "в " + MONTHS_LOC[ws.month - 1];
  }

  /** Ближайшее начало любого окна расписания: {month, day} или null. */
  function nextOpens(schedule, now) {
    if (!Array.isArray(schedule)) return null;
    const nowKey = now.month * 100 + now.date;
    let best = null, bestDist = Infinity;
    for (const rule of schedule) {
      const ws = windowStart(rule);
      if (!ws) continue;
      let key = ws.month * 100 + ws.day;
      if (key < nowKey) key += 1300;      // старт уже прошёл — ждём следующий год
      const dist = key - nowKey;
      if (dist < bestDist) { bestDist = dist; best = ws; }
    }
    return best;
  }

  /**
   * Статус объекта: { known, open, reason, [from, to], [opens] }.
   * known=false — расписания нет, судить не о чем (пляжи, мысы).
   */
  function status(place, date) {
    const schedule = place && place.schedule;
    if (!Array.isArray(schedule) || !schedule.length) {
      return { known: false, open: false, reason: "no-schedule" };
    }
    const now = crimeaNow(date);
    const rule = ruleFor(schedule, now.month, now.date);
    if (!rule) {
      const opens = formatOpens(nextOpens(schedule, now));
      return { known: true, open: false, reason: "season", opens: opens || null };
    }
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
    if (s.reason === "season") {
      return s.opens
        ? `🔴 Закрыто · открывается ${s.opens}`
        : "🔴 Закрыто в этом сезоне";
    }
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
    TZ_OFFSET_MIN, DAYS, MONTHS_GEN, MONTHS_LOC,
    crimeaNow, toMinutes, monthInRange, dayInWindow, ruleFor, windowStart,
    nextOpens, status, isOpen, label, filterOpen,
  };
});
