/* Тесты модуля интерактивной карты (static/leaflet-map.js).
   Запускаются в Node без DOM и без Leaflet — тестируем только
   экспортированные константы и хелперы. Поведение с реальной
   картой покрывается ассет-тестами на бэкенде. */
const test = require("node:test");
const assert = require("node:assert/strict");

const LM = require("../../static/leaflet-map.js");

test("константы: центр Крыма, дефолтный зум и диапазон", () => {
  assert.ok(Array.isArray(LM.CENTER));
  assert.equal(LM.CENTER.length, 2);
  assert.ok(LM.CENTER[0] > 44 && LM.CENTER[0] < 46, "широта центра в Крыму");
  assert.ok(LM.CENTER[1] > 33 && LM.CENTER[1] < 37, "долгота центра в Крыму");
  assert.equal(LM.ZOOM_DEFAULT, 8);
  assert.ok(LM.ZOOM_MIN < LM.ZOOM_DEFAULT);
  assert.ok(LM.ZOOM_MAX > LM.ZOOM_DEFAULT);
});

test("цвета типов согласованы с палитрой маркеров SVG", () => {
  /* Модуль знает все основные типы точек каталога — иначе маркеры
     будут серого цвета. Список типов см. app/data/types.json. */
  const must = ["beach", "castle", "palace", "winery", "nature",
                "park", "city", "spa", "food", "museum", "active", "factory"];
  for (const t of must) {
    assert.ok(LM._STYLE_COLORS[t], `цвет для типа "${t}" задан`);
    assert.match(LM._STYLE_COLORS[t], /^#[0-9a-f]{6}$/i,
      `${t} — валидный hex-цвет`);
  }
});

test("_iconConfig: собирает конфиг divIcon с правильным размером и якорем", () => {
  const icon = LM._iconConfig("beach", "🏖");
  assert.equal(typeof icon, "object");
  assert.equal(icon.className, "lm-marker");
  assert.ok(icon.html.includes("lm-pin"), "html содержит класс булавки");
  assert.ok(icon.html.includes("🏖"), "html содержит эмодзи");
  assert.ok(icon.html.includes(LM._STYLE_COLORS.beach), "html содержит цвет типа");
  /* Якорь упирается в низ булавки (не в центр), чтобы указывать на точку. */
  assert.deepEqual(icon.iconSize, [28, 36]);
  assert.equal(icon.iconAnchor[0], 14);
  assert.ok(icon.iconAnchor[1] > 30, "якорь внизу булавки");
});

test("неизвестный тип получает дежурный серый цвет, не падает", () => {
  const icon = LM._iconConfig("unknown-type-xyz", "❓");
  assert.ok(icon.html.includes("#64748b"), "неизвестный тип — серый");
  assert.ok(icon.html.includes("❓"));
});

test("экспорты присутствуют: createOrUpdate, destroy, loadLeaflet", () => {
  assert.equal(typeof LM.createOrUpdate, "function");
  assert.equal(typeof LM.destroy, "function");
  assert.equal(typeof LM.loadLeaflet, "function");
});
