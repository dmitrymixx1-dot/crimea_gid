/* Крым.Гид — фильтры каталога в URL `#/catalog?tag=&area=&q=&sort=`.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.CatalogLink) и тестируются в Node через node:test.
   Дефолтные значения в ссылку не пишутся — ссылка остаётся короткой. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CatalogLink = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const DEFAULTS = { tag: "", area: "", q: "", sort: "rating" };
  const KEYS = ["tag", "area", "q", "sort"];
  const SORTS = ["rating", "name", "time", "budget"];

  function decode(value) {
    try {
      return decodeURIComponent(value.replace(/\+/g, " "));
    } catch (e) {
      return "";  // битый percent-encoding — считаем параметр пустым
    }
  }

  function buildCatalogQuery(f) {
    const parts = [];
    for (const k of KEYS) {
      const v = f && f[k] != null ? String(f[k]).trim() : "";
      if (v && v !== DEFAULTS[k]) parts.push(k + "=" + encodeURIComponent(v));
    }
    return parts.join("&");
  }

  function parseCatalogQuery(query) {
    const out = Object.assign({}, DEFAULTS);
    const s = String(query || "").replace(/^[?#]/, "");
    if (!s) return out;
    for (const chunk of s.split("&")) {
      if (!chunk) continue;
      const i = chunk.indexOf("=");
      const k = i === -1 ? chunk : chunk.slice(0, i);
      const v = i === -1 ? "" : decode(chunk.slice(i + 1)).trim();
      if (KEYS.includes(k) && v) out[k] = v;
    }
    if (!SORTS.includes(out.sort)) out.sort = DEFAULTS.sort;
    return out;
  }

  function catalogUrl(f, origin, pathname) {
    const q = buildCatalogQuery(f);
    return (origin || "") + (pathname || "/") + "#/catalog" + (q ? "?" + q : "");
  }

  return { DEFAULTS, KEYS, SORTS, buildCatalogQuery, parseCatalogQuery, catalogUrl };
});
