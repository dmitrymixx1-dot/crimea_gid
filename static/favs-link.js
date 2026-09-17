/* Крым.Гид — избранное в URL `#/favs?f=id1,id2`.
   Чистые функции без DOM: подключаются в браузере через <script>
   (как window.FavsLink) и тестируются в Node через node:test.

   Ссылка несёт только id мест каталога (slug: a-z, цифры, дефис).
   На стороне получателя признаются лишь те id, которые есть в его
   каталоге, — мусор и чужие идентификаторы тихо отбрасываются.
   Ссылка добавляет места к избранному получателя, но никогда не
   убирает его собственные: делимся подборкой, а не чистим браузер. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FavsLink = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const KEY = "f";
  const ID_RE = /^[a-z0-9][a-z0-9-]*$/;

  function cleanIds(ids) {
    const list = Array.isArray(ids) ? ids : [];
    const out = [];
    for (const raw of list) {
      if (typeof raw !== "string") continue;  // чужие типы — не наши id
      const id = raw.trim();
      if (ID_RE.test(id) && !out.includes(id)) out.push(id);
    }
    return out;
  }

  function buildFavsQuery(ids) {
    const clean = cleanIds(ids);
    if (!clean.length) return "";
    return KEY + "=" + clean.map(encodeURIComponent).join(",");
  }

  function parseFavsQuery(query, knownIds) {
    const known = new Set(cleanIds(knownIds));
    const out = [];
    const s = String(query || "").replace(/^[?#]/, "");
    if (!s) return out;
    for (const chunk of s.split("&")) {
      if (!chunk) continue;
      const i = chunk.indexOf("=");
      const k = i === -1 ? chunk : chunk.slice(0, i);
      if (k !== KEY) continue;
      const v = i === -1 ? "" : decodeSafe(chunk.slice(i + 1));
      for (const raw of v.split(",")) {
        const id = raw.trim();
        if (ID_RE.test(id) && known.has(id) && !out.includes(id)) out.push(id);
      }
    }
    return out;
  }

  /** Полный URL ссылки на избранное. Пусто, если делиться нечем. */
  function favsUrl(ids, origin, pathname) {
    const q = buildFavsQuery(ids);
    if (!q) return "";
    return (origin || "") + (pathname || "/") + "#/favs?" + q;
  }

  function decodeSafe(value) {
    try {
      return decodeURIComponent(value);
    } catch (e) {
      return value;  // битый percent-encoding — работаем с сырым значением
    }
  }

  return { KEY, ID_RE, cleanIds, buildFavsQuery, parseFavsQuery, favsUrl };
});
