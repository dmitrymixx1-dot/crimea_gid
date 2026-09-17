/* Крым.Гид — вторая речь (английская локаль ключевых экранов).
   Чистые функции без зависимостей от DOM: в браузере — window.I18n,
   в Node тестируются через node:test.

   Как это работает и почему именно так:

   1. Ключ словаря — САМА русская фраза, а не выдуманное имя. Русская
      строка остаётся в коде и в разметке, поэтому интерфейс читаем без
      словаря, а новый текст без перевода просто остаётся русским
      (деградация вместо «переведено наполовину»).

   2. Перевод накладывается на уже отрисованный DOM (`localize`), а не
      вплетается в каждый шаблон: экраны собраны строками-шаблонами, и
      обёртывать каждую строку в `t()` значило бы раздуть правку в разы.
      Точка одна — после отрисовки.

   3. Числа в подписях складываются в шаблон: «⏱ 2 ч» и «Показано 12 из 47»
      DOM отдаёт одним текстовым узлом, точным ключом его не поймать.
      `fold()` заменяет числовые группы на `{n}`, а `t()` возвращает их в
      перевод по порядку. Русские формы множественного числа остаются в
      словаре отдельными ключами — из них и следует английское
      «1 refresh» / «2 refreshes», правил счёта в модуле нет.
*/
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.I18n = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LANGS = ["ru", "en"];
  // Родная речь приложения: если ни URL, ни браузер, ни сохранённый выбор
  // ничего не сказали, показываем русский, а не «международную заглушку».
  const DEFAULT_LANG = "ru";
  const LOCALE = { ru: "ru-RU", en: "en-GB" };
  const STORAGE_KEY = "crimea_lang";
  const BUNDLE_URL = "/static/i18n/en.json";
  // Атрибуты, которые тоже видно человеку: `alt` — доступность, `title` и
  // `placeholder` — подсказки, `aria-label` — имя элемента для скринридера
  // (без него кнопка «✕» остаётся «✕» и для англичанина).
  const TRANSLATE_ATTRS = ["title", "aria-label", "placeholder", "alt"];
  // Что в дереве не трогаем: текст скриптов и стилей — это код, а
  // `textarea` хранит ввод пользователя.
  const SKIP_TAGS = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, NOSCRIPT: 1 };
  const SKIP_ATTR = "data-i18n";
  const SKIP_VALUE = "skip";
  // Числовая группа — та же, что в `tools/i18n_extract.py` (NUMBER_RE):
  // «0,4», «10:00», «3–5», «1 000». Разделители внутри группы, а не между
  // числами: иначе «10:00–19:00» свернулось бы в три `{n}` вместо одного.
  const NUMBER_RE = /\d+(?:[.,:–— -]\d+)*/g;
  const WS_RE = /\s+/g;
  const PLACEHOLDER = "{n}";

  /** Та же нормализация, что делает текстовый узел: пробелы схлопнуты, края срезаны. */
  function normalize(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(WS_RE, " ")
      .trim();
  }

  /**
   * Сложить числа в шаблон: «Показано 12 из 47» → ключ «Показано {n} из {n}»
   * и числа [12, 47], которые вернутся в перевод по порядку.
   */
  function fold(text) {
    const source = normalize(text);
    if (!/\d/.test(source)) return { key: source, nums: [] };
    const nums = source.match(NUMBER_RE) || [];
    return { key: source.replace(NUMBER_RE, PLACEHOLDER), nums };
  }

  /** Десятичная запятая живёт только в русской записи: 0,4 м → 0.4 m. */
  function numberForLang(value, lang) {
    return lang === "ru" ? value : String(value).replace(",", ".");
  }

  /**
   * Собрать перевод: `{n}` — числа из `fold()` по порядку, `{имя}` —
   * явная подстановка из `params` (для строк, вынесенных в `t()` в коде).
   */
  function fill(template, nums, params, lang) {
    const put = index =>
      nums[index] === undefined ? null : numberForLang(nums[index], lang);
    let seen = 0;
    const out = template.replace(/\{n\d*\}/g, token => {
      const value = token.length > 3 ? put(Number(token.slice(2, -1)) - 1) : put(seen);
      seen += 1;
      return value === null ? token : value;
    });
    if (!params) return out;
    return out.replace(/\{(\w+)\}/g, (all, name) =>
      params[name] === undefined || params[name] === null ? all : String(params[name])
    );
  }

  /* ---------------- состояние ---------------- */
  // Один экземпляр на страницу: переключение языка обязано подействовать на
  // весь следующий рендер, а не на один вызов.
  const state = { lang: DEFAULT_LANG, ui: null };

  function lang() {
    return state.lang;
  }

  function isEnglish() {
    return state.lang === "en";
  }

  /** Intl-локаль речи: ею форматируют время и даты (`fmtTime` в app.js). */
  function locale() {
    return LOCALE[state.lang] || "ru-RU";
  }

  /**
   * Словарь обходчика из бандла: `labels` (подписи данных, сервисов и
   * модулей) плюс `ui` (строки разметки). Порядок важен: разметка ближе к
   * DOM, поэтому её ключ главнее. Бандла нет — возвращаем null, и обходчик
   * остаётся на русском; голый словарь (без секций) принимается как есть —
   * так удобно проверять модуль в тестах.
   */
  function dictFrom(bundle) {
    if (!bundle || typeof bundle !== "object") return null;
    if (bundle.ui || bundle.labels) {
      return { ...(bundle.labels || {}), ...(bundle.ui || {}) };
    }
    return Object.keys(bundle).length ? bundle : null;
  }

  /** Сменить речь. Русскому словарь не нужен — он и есть оригинал. */
  function setLang(next, bundle) {
    state.lang = LANGS.indexOf(next) === -1 ? DEFAULT_LANG : next;
    if (bundle) state.ui = dictFrom(bundle);
    else if (state.lang === "ru") state.ui = null;
    return state.lang;
  }

  /** Поставить словарь RU → EN (бандл целиком) — до первого рендера. */
  function install(bundle) {
    state.ui = dictFrom(bundle);
    return state.ui !== null;
  }

  /**
   * Строка на текущем языке: сначала точный ключ, затем — с числами,
   * свёрнутыми в `{n}`.
   *
   * Порядок важен: «3–5 дней» и «6–10 дней» после сворачивания — один и
   * тот же ключ, поэтому данные переводим буквально, а складывание
   * чисел остается запасным путем для подписей, собранных из кусков
   * («через 5 минут», «купаться опасно: волна 1,5 м»).
   *
   * Нет ключа — возвращаем исходник: половина экрана без перевода лучше,
   * чем пустая подпись. `params` подставляются в обе стороны — и в
   * перевод, и в русский оригинал, иначе `{step}` утёк бы в интерфейс
   * на родной речи, где словаря нет вовсе.
   */
  function translate(text, params) {
    const raw = String(text === undefined || text === null ? "" : text);
    const ui = state.ui;
    if (!ui) return fill(raw, [], params, state.lang);
    const exact = normalize(raw);
    if (exact in ui) return fill(ui[exact], [], params, state.lang);
    const { key, nums } = fold(raw);
    if (key in ui) return fill(ui[key], nums, params, state.lang);
    return fill(raw, [], params, state.lang);
  }

  /** Есть ли у строки перевод (точным ключом или свёрнутым) — для тестов. */
  function has(text) {
    if (!state.ui) return false;
    const exact = normalize(text);
    return exact in state.ui || fold(text).key in state.ui;
  }

  /* ---------------- выбор языка ---------------- */
  /**
   * Какую речь показывать: явный `?lang=` важнее сохранённого выбора,
   * сохранённый — важнее настроек браузера. Неизвестное значение — родной
   * язык, а не «попробуем английский».
   */
  function pickLang(options) {
    const opts = options || {};
    const wanted = [opts.url, opts.stored, ...(opts.nav || [])];
    for (const raw of wanted) {
      const value = normalize(raw).toLowerCase();
      if (!value) continue;
      if (LANGS.indexOf(value) !== -1) return value;
      const base = value.split("-")[0];
      if (LANGS.indexOf(base) !== -1) return base;
    }
    return DEFAULT_LANG;
  }

  /** Языки браузера: `navigator.languages` с фолбэком на `navigator.language`. */
  function navLangs(nav) {
    if (!nav) return [];
    if (Array.isArray(nav.languages) && nav.languages.length) return nav.languages;
    return nav.language ? [nav.language] : [];
  }

  /* ---------------- обход DOM ---------------- */
  function children(node) {
    if (!node) return [];
    const list = node.childNodes !== undefined ? node.childNodes : node.children;
    return list ? Array.prototype.slice.call(list) : [];
  }

  function skipped(node) {
    if (SKIP_TAGS[String(node.tagName || "").toUpperCase()]) return true;
    return (
      typeof node.getAttribute === "function" &&
      node.getAttribute(SKIP_ATTR) === SKIP_VALUE
    );
  }

  /**
   * Перевести поддерево на месте; вернуть число заменённых кусков.
   *
   * Ноль — словарь не понадобился (русская речь или пустой экран), и это
   * не ошибка. Обход идемпотентен: английская фраза не является ключом,
   * поэтому повторный проход ничего не трогает, а переключение на `ru`
   * просто возвращает исходный рендер.
   */
  function localize(root) {
    if (!root || !state.ui) return 0;
    let changed = 0;
    const stack = [root];
    while (stack.length) {
      const node = stack.pop();
      if (node.nodeType === 3) {
        const source = node.nodeValue;
        const next = translate(source);
        if (next !== source) {
          // Пробелы вокруг значения — часть разметки, сохраняем их как были.
          const edge = /^(\s*)[\s\S]*?(\s*)$/.exec(source);
          node.nodeValue = (edge ? edge[1] : "") + normalize(next) + (edge ? edge[2] : "");
          changed++;
        }
        continue;
      }
      if (node.nodeType !== 1 || skipped(node)) continue;
      if (typeof node.getAttribute === "function") {
        for (const name of TRANSLATE_ATTRS) {
          const value = node.getAttribute(name);
          if (!value) continue;
          const next = translate(value);
          if (next !== value) {
            node.setAttribute(name, next);
            changed++;
          }
        }
      }
      const kids = children(node);
      for (let i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
    }
    return changed;
  }

  /**
   * Язык документа: `lang` читает скринридер, `title` виден во вкладке.
   * Вызываем и после старта, и при смене языка — каркас сервер отдаёт
   * по-русски, и без этого переключения англоязычная страница осталась бы
   * «русской» для программ чтения с экрана.
   */
  function applyDoc(doc) {
    if (!doc || !doc.documentElement) return false;
    doc.documentElement.setAttribute("lang", state.lang);
    if (doc.title) doc.title = translate(doc.title) || doc.title;
    return true;
  }

  /* ---------------- данные: перевод поверх записей ---------------- */
  /**
   * Накладывать перевод на записи каталога (см. `places` в бандле).
   *
   * Имена мест и описания приходят из данных, а не из кода, и ключ — id
   * записи: строка названия могла поехать и в новость, и в поиск.
   * Оригинальные значения остаются в `<поле>_ru` — по ним ищет человек,
   * набравший «Ласточкино» на уже английском экране.
   */
  function applyLabels(items, labels, fields) {
    if (!labels || !Array.isArray(items)) return items || [];
    for (const item of items) {
      const entry = labels[item.id];
      if (!entry) continue;
      for (const field of fields) {
        const value = entry[field];
        if (typeof value !== "string" || !value) continue;
        const original = item[field];
        if (original === undefined || original === null || original === "") continue;
        // Пустое поле в данных не выдумываем: английская карточка не должна
        // быть длиннее русской (часов нет — и в переводе их быть не может).
        // Оригинальный текст храним ровно один раз: повторный вызов (новая
        // выдача квиза, повторное включение языка) не должен принять
        // перевод за оригинал.
        if (item[`${field}_ru`] === undefined) item[`${field}_ru`] = original;
        item[field] = value;
      }
    }
    return items;
  }

  /** Вернуть русские оригиналы — то же самое при возврате на `ru`. */
  function stripLabels(items, fields) {
    if (!Array.isArray(items)) return items || [];
    for (const item of items) {
      for (const field of fields) {
        const key = `${field}_ru`;
        if (item[key] === undefined) continue;
        item[field] = item[key];
        delete item[key];
      }
    }
    return items;
  }

  return {
    LANGS,
    DEFAULT_LANG,
    LOCALE,
    STORAGE_KEY,
    BUNDLE_URL,
    TRANSLATE_ATTRS,
    PLACEHOLDER,
    normalize,
    fold,
    numberForLang,
    fill,
    lang,
    isEnglish,
    locale,
    setLang,
    dictFrom,
    install,
    translate,
    has,
    pickLang,
    navLangs,
    localize,
    applyDoc,
    applyLabels,
    stripLabels,
  };
});
