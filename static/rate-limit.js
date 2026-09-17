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

  /** Целое из заголовка; пусто или мусор → null. */
  function intOrNull(value) {
    const raw = String(value === undefined || value === null ? "" : value).trim();
    if (!raw) return null;
    const n = Number(raw);
    if (!isFinite(n) || n < 0) return null;
    return Math.round(n);
  }

  /** Бюджет из заголовков X-RateLimit-*: {rule, limit, remaining, reset}.
      Ждём настоящие Headers ответа (`res.headers`): заголовка нет —
      поля нет, а если сервер не сказал ничего — null, а не выдуманный
      лимит из воздуха. `rule` — имя бюджета (лента, погода, квиз…):
      у каждой ручки он свой, и складывать их в одну кучу нельзя. */
  function readBudget(headers) {
    if (!headers || typeof headers.get !== "function") return null;
    const rule = String(headers.get("X-RateLimit-Rule") || "").trim();
    const budget = {
      rule: rule || null,
      limit: intOrNull(headers.get("X-RateLimit-Limit")),
      remaining: intOrNull(headers.get("X-RateLimit-Remaining")),
      reset: intOrNull(headers.get("X-RateLimit-Reset")),
    };
    if (
      budget.limit === null &&
      budget.remaining === null &&
      budget.reset === null
    ) {
      return null;
    }
    return budget;
  }

  /** Сколько секунд кнопку лучше не трогать: 0 — можно.
      Считаем и исчерпанный бюджет (remaining 0 → ждём очистки окна),
      и прямой отказ (Retry-After): смысл один — запрос всё равно
      кончится 429, а бюджет только потратится. */
  function cooldownSeconds(budget, retryAfter) {
    let wait = parseRetryAfter(retryAfter) || 0;
    if (budget && budget.remaining === 0) {
      const reset = parseRetryAfter(budget.reset);
      if (reset) wait = Math.max(wait, reset);
    }
    return wait;
  }

  /** Подпись остатка бюджета: «осталось 2 обновления из 6», а на нуле —
      «обновления исчерпаны» (ноль остатка читается как ошибка, а не как
      факт). Полный бюджет и незнакомая ручка молчат — сообщать нечего. */
  function budgetText(budget) {
    if (!budget || budget.remaining === null || budget.limit === null) return "";
    if (budget.remaining <= 0) return "обновления исчерпаны";
    if (budget.remaining >= budget.limit) return "";
    const forms = ["обновление", "обновления", "обновлений"];
    return `осталось ${budget.remaining} ${plural(budget.remaining, forms)} из ${budget.limit}`;
  }

  return {
    parseRetryAfter,
    plural,
    waitText,
    message,
    intOrNull,
    readBudget,
    cooldownSeconds,
    budgetText,
    MAX_SECONDS,
    MINUTE,
  };
});
