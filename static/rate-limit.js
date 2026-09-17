/* Крым.Гид — ответ «слишком много запросов» (429).
   Чистые функции без DOM: в браузере — window.RateLimit,
   в Node тестируются через node:test.

   Порог и подписи живут здесь, а не в app.js: правила покрыты тестами,
   а текстами пользуются все ручки, которые умеют отвечать 429.

   Ожидание берём из заголовка Retry-After, а не выдумываем: сервер
   знает, когда освободится слот, а клиент — нет. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RateLimit = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MAX_SECONDS = 3600;   // ждать дольше часа бессмысленно — обрываем
  const MINUTE = 60;

  /** Секунды ожидания из заголовка Retry-After; мусор → null. */
  function parseRetryAfter(value) {
    const raw = String(value === undefined || value === null ? "" : value).trim();
    if (!raw) return null;
    const n = Number(raw);
    if (!isFinite(n) || n < 0) return null;   // HTTP-дату не обещаем
    return Math.min(Math.round(n), MAX_SECONDS);
  }

  /** Русские формы: plural(2, ["минуту", "минуты", "минут"]) → "минуты". */
  function plural(n, forms) {
    const mod10 = Math.abs(n) % 10;
    const mod100 = Math.abs(n) % 100;
    if (mod10 === 1 && mod100 !== 11) return forms[0];
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
    return forms[2];
  }

  /** «через 30 с», «через минуту», «через 5 минут»; нет данных → "". */
  function waitText(seconds) {
    const s = parseRetryAfter(seconds);
    if (s === null || s <= 0) return "";
    if (s < MINUTE) return `через ${s} с`;
    const m = Math.ceil(s / MINUTE);
    return `через ${m} ${plural(m, ["минуту", "минуты", "минут"])}`;
  }

  /** Текст тоста: с временем ожидания, если сервер его прислал. */
  function message(retryAfter) {
    const wait = waitText(retryAfter);
    return wait
      ? `Слишком часто. Попробуйте ${wait}.`
      : "Слишком часто. Попробуйте позже.";
  }

  return { parseRetryAfter, plural, waitText, message, MAX_SECONDS, MINUTE };
});
