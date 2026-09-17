// Юнит-тесты второй речи (static/i18n.js): сворачивание чисел, порядок
// поиска ключа, обход DOM и перевод данных. Запуск:
//   node --test "tests/js/*.test.js"
// Зависимостей нет: модуль чистый, DOM подменяем крошечными фейками.
const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const I = require("../../static/i18n.js");

/* ---------------- фейковый DOM ---------------- */

function text(value) {
  return { nodeType: 3, nodeValue: value };
}

function el(tag, kids, attrs) {
  const a = Object.assign({}, attrs);
  return {
    nodeType: 1,
    tagName: tag,
    childNodes: kids || [],
    getAttribute: name => (name in a ? a[name] : null),
    setAttribute: (name, value) => { a[name] = value; },
    _attrs: a,
  };
}

/* ---------------- сворачивание чисел ---------------- */

describe("i18n: normalize и fold", () => {
  it("схлопывает пробелы — как текстовый узел в DOM", () => {
    assert.equal(I.normalize("\n  Каталог   мест \n"), "Каталог мест");
    assert.equal(I.normalize(null), "");
    assert.equal(I.normalize(undefined), "");
  });

  it("складывает в {n} каждое число, а не каждую цифру", () => {
    assert.deepEqual(I.fold("Показано 12 из 47"), {
      key: "Показано {n} из {n}", nums: ["12", "47"],
    });
    assert.deepEqual(I.fold("⏱ 2 ч"), { key: "⏱ {n} ч", nums: ["2"] });
    assert.deepEqual(I.fold("Каталог мест"), { key: "Каталог мест", nums: [] });
  });

  it("группы чисел — разделители внутри, а не между", () => {
    // Часы работы: «10:00–19:00» — одна группа, иначе ключ разошёлся бы с
    // подписью словаря (в русском исходнике тоже одна вставка).
    assert.deepEqual(I.fold("до 10:00–19:00"), { key: "до {n}", nums: ["10:00–19:00"] });
    // Десятичная запятая — русская запись: 0,4 м остаётся одним числом.
    assert.deepEqual(I.fold("волна 1,7 м"), { key: "волна {n} м", nums: ["1,7"] });
  });

  /* Совпадение `NUMBER_RE` с регуляркой tools/i18n_extract.py проверяет
     tests/test_i18n.py — там читать исходники удобнее. */

  it("числа возвращаются в перевод по порядку, запятая становится точкой", () => {
    assert.equal(I.fill("{n} из {n}", ["12", "47"], null, "en"), "12 из 47");
    assert.equal(I.fill("{n1} of {n2}", ["3", "5"], null, "en"), "3 of 5");
    assert.equal(I.fill("wave {n} m", ["1,7"], null, "en"), "wave 1.7 m");
    assert.equal(I.fill("волна {n} м", ["1,7"], null, "ru"), "волна 1,7 м");
    // Нет числа — оставляем шаблон как есть: лучше половина подписи, чем пустая.
    assert.equal(I.fill("осталось {n}", [], null, "en"), "осталось {n}");
  });

  it("params подставляются и в перевод, и в русский оригинал", () => {
    assert.equal(I.fill("{a} · {b}", [], { a: 1, b: null }, "en"), "1 · {b}");
  });
});

/* ---------------- словарь и поиск ---------------- */

describe("i18n: словарь", () => {
  it("бандл складывается из labels и ui, разметка главнее", () => {
    const dict = I.dictFrom({
      labels: { А: "a", Общий: "from labels" },
      ui: { Общий: "from ui", Б: "b" },
    });
    assert.deepEqual(dict, { А: "a", Общий: "from ui", Б: "b" });
    assert.equal(I.dictFrom(null), null);
    assert.deepEqual(I.dictFrom({ "Каталог": "Catalogue" }), { Каталог: "Catalogue" });
    assert.equal(I.dictFrom({}), null, "пустой словарь — это не словарь");
  });

  it("точный ключ важнее свёрнутого", () => {
    // Данные («3–5 дней» и «6–10 дней») после сворачивания неразличимы,
    // поэтому для них обязан работать буквальный ключ.
    I.setLang("en", {
      "3–5 дней": "3–5 days",
      "через {n} минут": "in {n} minutes",
      "купаться опасно: волна {n} м": "dangerous to swim: wave {n} m",
    });
    assert.equal(I.translate("3–5 дней"), "3–5 days");
    // «6–10 дней» сворачивается в тот же «{n} дней», что и «3–5 дней»:
    // угадывать по свёрнутому ключу нельзя, поэтому данных и касается только
    // буквальный ключ, а остальное честно остаётся русским.
    assert.equal(I.translate("6–10 дней"), "6–10 дней");
    assert.equal(I.translate("через 7 минут"), "in 7 minutes");
    assert.equal(I.translate("купаться опасно: волна 1,7 м"),
      "dangerous to swim: wave 1.7 m");
    assert.equal(I.has("3–5 дней"), true);
    assert.equal(I.has("нет такого"), false);
  });

  it("без ключа возвращает исходник, с params — и в исходнике", () => {
    I.install({ "Показано ещё {n}": "Show {n} more" });
    assert.equal(I.translate("Что-то новенькое"), "Что-то новенькое");
    assert.equal(I.translate("Показано ещё 3"), "Show 3 more");
    assert.equal(I.translate(null), "");
    assert.equal(I.translate("обновлено {time}{failed}", { time: "14:05", failed: "" }),
      "обновлено 14:05");
  });

  it("на русской речи словаря нет вовсе — и не нужно", () => {
    I.setLang("ru");
    assert.equal(I.has("Каталог мест"), false);
    assert.equal(I.translate("Каталог мест"), "Каталог мест");
    I.setLang("en", { ui: { "Каталог мест": "Catalogue" } });
    assert.equal(I.translate("Каталог мест"), "Catalogue");
    I.setLang("ru");   // вернулись — и словарь снялся, и строка стала родной
    assert.equal(I.translate("Каталог мест"), "Каталог мест");
  });

  it("неизвестный язык — русский, а не «попробуем английский»", () => {
    assert.equal(I.setLang("de", { ui: { А: "b" } }), "ru");
    assert.equal(I.lang(), "ru");
    assert.equal(I.locale(), "ru-RU");
    I.setLang("en");
    assert.equal(I.isEnglish(), true);
    assert.equal(I.locale(), "en-GB");
  });
});

/* ---------------- выбор речи ---------------- */

describe("i18n: какую речь включать", () => {
  it("ссылка важнее сохранённого выбора, сохранённый — браузера", () => {
    assert.equal(I.pickLang({ url: "en", stored: "ru", nav: ["en-US"] }), "en");
    assert.equal(I.pickLang({ url: "", stored: "en", nav: ["ru"] }), "en");
    assert.equal(I.pickLang({ stored: "", nav: ["de", "en-GB"] }), "en");
    assert.equal(I.pickLang({}), "ru");
    assert.equal(I.pickLang({ url: "fr" }), "ru", "неизвестный язык — родной");
  });

  it("базовый подтег допустим: en-US → en", () => {
    assert.equal(I.pickLang({ nav: ["en-US"] }), "en");
    assert.equal(I.pickLang({ url: "RU" }), "ru");
  });

  it("список языков браузера: languages с фолбэком на language", () => {
    assert.deepEqual(I.navLangs({ languages: ["de", "en"] }), ["de", "en"]);
    assert.deepEqual(I.navLangs({ language: "en" }), ["en"]);
    assert.deepEqual(I.navLangs({ languages: [] , language: "fr" }), ["fr"]);
    assert.deepEqual(I.navLangs(null), []);
  });
});

/* ---------------- обход DOM ---------------- */

describe("i18n: localize", () => {
  const DICT = {
    "Каталог мест": "Catalogue",
    "Смотреть все": "See all",
    "Поиск по названию": "Search by name",
  };

  it("меняет текстовые узлы и переводимые атрибуты", () => {
    I.install(DICT);
    const card = el("article", [el("h3", [text("Каталог мест")]), text(" Смотреть все ")],
      { title: "Каталог мест", "aria-label": "Каталог мест", "data-x": "Каталог мест" });
    const changed = I.localize(card);
    assert.equal(changed, 4, "два узла + два атрибута, но data-* не трогаем");
    assert.equal(card.childNodes[0].childNodes[0].nodeValue, "Catalogue");
    assert.equal(card.childNodes[1].nodeValue, " See all ", "пробелы разметки на месте");
    assert.equal(card._attrs.title, "Catalogue");
    assert.equal(card._attrs["aria-label"], "Catalogue");
    assert.equal(card._attrs["data-x"], "Каталог мест");
  });

  it("placeholder и alt тоже переводятся", () => {
    I.install(DICT);
    const input = el("input", [], { placeholder: "Поиск по названию" });
    const img = el("img", [], { alt: "Каталог мест" });
    const root = el("div", [input, img]);
    assert.equal(I.localize(root), 2);
    assert.equal(input._attrs.placeholder, "Search by name");
    assert.equal(img._attrs.alt, "Catalogue");
  });

  it("не лезет в скрипт, стиль, textarea и в data-i18n=skip", () => {
    I.install(DICT);
    const script = el("script", [text("Каталог мест")]);
    const style = el("style", [text("Каталог мест")]);
    const area = el("textarea", [text("Каталог мест")], { title: "Каталог мест" });
    const skip = el("div", [text("Каталог мест")], { "data-i18n": "skip", title: "Каталог мест" });
    const root = el("div", [script, style, area, skip, text("Каталог мест")]);
    assert.equal(I.localize(root), 1, "только последний узел — настоящий текст");
    assert.equal(script.childNodes[0].nodeValue, "Каталог мест");
    assert.equal(area.childNodes[0].nodeValue, "Каталог мест");
    assert.equal(skip.childNodes[0].nodeValue, "Каталог мест");
    assert.equal(skip._attrs.title, "Каталог мест");
    assert.equal(root.childNodes[4].nodeValue, "Catalogue");
  });

  it("идемпотентен: второй проход ничего не меняет", () => {
    I.install(DICT);
    const root = el("section", [text("Каталог мест"), el("a", [text("Смотреть все")])]);
    assert.ok(I.localize(root) > 0);
    assert.equal(I.localize(root), 0, "английская фраза — не ключ, обратного хода нет");
    assert.equal(I.localize(root), 0);
  });

  it("на русской речи и без словаря — no-op", () => {
    I.setLang("ru");
    const root = el("div", [text("Каталог мест")]);
    assert.equal(I.localize(root), 0);
    assert.equal(root.childNodes[0].nodeValue, "Каталог мест");
    assert.equal(I.localize(null), 0);
  });

  it("числа в узле находят свёрнутый ключ", () => {
    I.install({ "Показано {n} из {n}": "Shown {n1} of {n2}" });
    const node = text("Показано 24 из 60");
    I.localize(el("div", [node]));
    assert.equal(node.nodeValue, "Shown 24 of 60");
  });

  it("lang и title документа едут за рендером", () => {
    const doc = { documentElement: el("html", []), title: "Каталог мест — Крым.Гид" };
    I.setLang("en", { ui: { "Каталог мест — Крым.Гид": "Catalogue — Крым.Гид" } });
    assert.equal(I.applyDoc(doc), true);
    assert.equal(doc.documentElement._attrs.lang, "en");
    assert.equal(doc.title, "Catalogue — Крым.Гид");
    I.setLang("ru");
    assert.equal(I.applyDoc(doc), true);
    assert.equal(doc.documentElement._attrs.lang, "ru");
    assert.equal(doc.title, "Catalogue — Крым.Гид", "на русском оригинала менять нечего");
    assert.equal(I.applyDoc(null), false);
  });
});

/* ---------------- перевод данных ---------------- */

describe("i18n: applyLabels и stripLabels", () => {
  const FIELDS = ["name", "region", "description"];
  const LABELS = {
    lastochino: { name: "Swallow's Nest", region: "Yalta", description: "A castle on a cliff" },
    sudak: { name: "Genoese Fortress" },
  };

  it("кладёт перевод поверх записей, оригинал остаётся в <поле>_ru", () => {
    const items = [
      { id: "lastochino", name: "Ласточкино гнездо", region: "Ялта", description: "Замок" },
      { id: "sudak", name: "Крепость", region: "Судак", description: "Генуэзцы" },
      { id: "novoe", name: "Новое место", region: "Где-то", description: "—" },
    ];
    I.applyLabels(items, LABELS, FIELDS);
    assert.equal(items[0].name, "Swallow's Nest");
    assert.equal(items[0].name_ru, "Ласточкино гнездо");
    assert.equal(items[0].description_ru, "Замок");
    assert.equal(items[1].region, "Судак", "поля нет в переводе — остаётся русским");
    assert.equal("region_ru" in items[1], false);
    assert.equal(items[0].description, "A castle on a cliff");
    assert.equal(items[0].description_ru, "Замок", "оригинал нужен поиску на английском экране");

    // Поля, которого в данных нет, перевод не выдумывает: английская
    // карточка не может быть длиннее русской.
    const sparse = [{ id: "lastochino", name: "Ласточкино гнездо" }];
    I.applyLabels(sparse, LABELS, FIELDS);
    assert.equal("description" in sparse[0], false);
    assert.equal("region" in sparse[0], false);
    assert.equal(items[2].name, "Новое место", "места нет в словаре — не трогаем");
    assert.equal(items[2].name_ru, undefined);
  });

  it("повторный вызов не принимает перевод за оригинал", () => {
    const items = [{ id: "lastochino", name: "Ласточкино гнездо" }];
    I.applyLabels(items, LABELS, ["name"]);
    I.applyLabels(items, LABELS, ["name"]);
    assert.equal(items[0].name_ru, "Ласточкино гнездо");
    assert.equal(items[0].name, "Swallow's Nest");
  });

  it("stripLabels возвращает русский и убирает служебное поле", () => {
    const items = [{ id: "lastochino", name: "Ласточкино гнездо", region: "Ялта" }];
    I.applyLabels(items, LABELS, FIELDS);
    I.stripLabels(items, FIELDS);
    assert.equal(items[0].name, "Ласточкино гнездо");
    assert.equal(items[0].region, "Ялта");
    assert.equal("name_ru" in items[0], false);
    assert.equal("description_ru" in items[0], false);
  });

  it("пустые и чужие входы не ломают обход", () => {
    assert.deepEqual(I.applyLabels([], LABELS, FIELDS), []);
    assert.deepEqual(I.applyLabels(null, LABELS, FIELDS), []);
    assert.deepEqual(I.applyLabels([{ id: "x", name: "А" }], null, FIELDS)[0].name, "А");
    assert.deepEqual(I.stripLabels(undefined, FIELDS), []);
    const broken = [{ id: "lastochino", name: "Ласточкино гнездо" }];
    I.applyLabels(broken, { lastochino: { name: "" } }, FIELDS);
    assert.equal(broken[0].name, "Ласточкино гнездо", "пустая строка — не перевод");
  });
});

/* ---------------- константы ---------------- */

describe("i18n: контракт статики", () => {
  it("бандл качается по адресу из модуля, а не из воздуха", () => {
    const html = fs.readFileSync(path.join(__dirname, "../../static/index.html"), "utf8");
    assert.ok(html.includes('src="/static/i18n.js"'), "модуль не подключён к каркасу");
    assert.equal(I.BUNDLE_URL, "/static/i18n/en.json");
    assert.deepEqual(I.LANGS, ["ru", "en"]);
    assert.equal(I.DEFAULT_LANG, "ru");
    assert.equal(I.STORAGE_KEY, "crimea_lang");
    assert.deepEqual(I.TRANSLATE_ATTRS, ["title", "aria-label", "placeholder", "alt"]);
    assert.equal(I.PLACEHOLDER, "{n}");
  });
});
