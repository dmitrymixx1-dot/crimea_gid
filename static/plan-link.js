/* Крым.Гид — сериализация ответа квиза в ссылку `#/quiz?plan=…`.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.PlanLink) и тестируются в Node через node:test. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PlanLink = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Порядок полей зафиксирован контрактом: buildPlanString и parsePlanParam
  // обязаны использовать один и тот же ORDER (проверяется тестами).
  const ORDER = ["purpose", "season", "tempo", "budget", "party", "duration", "transport"];

  function buildPlanString(a) {
    return ORDER.map(k =>
      k === "purpose" ? (a.purpose || []).join(",") : a[k]).join("~");
  }

  function parsePlanParam(str) {
    const p = (str || "").split("~");
    if (p.length !== ORDER.length) return null;
    const purpose = p[0].split(",").filter(Boolean);
    if (!purpose.length) return null;
    return {
      purpose,
      season: p[1], tempo: p[2], budget: p[3],
      party: p[4], duration: p[5], transport: p[6],
    };
  }

  return { ORDER, buildPlanString, parsePlanParam };
});
