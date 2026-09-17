const test = require("node:test");
const assert = require("node:assert/strict");
const { offsets } = require("../../static/map-layout.js");
const catalog = require("../../app/data/attractions.json");
const a = { id: "a", lat: 44.9597, lng: 35.2403 };
const b = { ...a, id: "b" };

test("пустой список и одиночные точки не смещаются", () => {
  assert.equal(offsets([]).size, 0);
  assert.deepEqual(offsets([a]).get("a"), { x: -0, y: 0, moved: false });
});

test("совпавшие координаты расходятся, исходные данные не меняются", () => {
  const items = [Object.freeze(a), Object.freeze(b)];
  const before = JSON.stringify(items);
  const result = offsets(items);
  const first = result.get("a"), second = result.get("b");
  assert.ok(Math.hypot(first.x - second.x, first.y - second.y) >= 43.99);
  assert.equal(first.moved, true);
  assert.equal(JSON.stringify(items), before);
});

test("порядок каталога и перевод названий не меняют раскладку", () => {
  assert.deepEqual(offsets([a, b]), offsets([{ ...b, name: "Wine" }, a]));
});

test("фильтр оставил одно место — маркер возвращается на координату", () => {
  assert.equal(offsets([a, b]).get("a").moved, true);
  assert.equal(offsets([a]).get("a").moved, false);
});

test("разные координаты не объединяются; повтор id в плане не создаёт дубль", () => {
  assert.equal(offsets([a, { ...b, lat: 44.9598 }]).get("a").moved, false);
  assert.deepEqual(offsets([a, a, b]), offsets([a, b]));
});

test("в группе 3+ мест соседние маркеры не накрывают друг друга", () => {
  for (const n of [3, 5, 12]) {
    const result = [...offsets(Array.from({ length: n }, (_, i) => ({ ...a, id: String(i) })), 48).values()];
    result.forEach((p, i) => result.slice(i + 1).forEach(q => {
      assert.ok(Math.hypot(p.x - q.x, p.y - q.y) >= 47.99);
    }));
  }
});

test("реальный каталог: обе точки Коктебеля доступны отдельно", () => {
  const items = Array.isArray(catalog) ? catalog : catalog.items;
  const pair = items.filter(p => p.lat === a.lat && p.lng === a.lng);
  assert.equal(pair.length, 2);
  const result = offsets(items);
  assert.ok(pair.every(p => result.get(p.id).moved));
  assert.notDeepEqual(result.get(pair[0].id), result.get(pair[1].id));
});

test("выноски не накрывают соседние точки в экранной проекции", () => {
  const neighbor = { id: "c", lat: 44.97, lng: 35.25 };
  const project = p => p.id === "c" ? { x: -44, y: 0 } : { x: 0, y: 0 };
  const result = offsets([a, b, neighbor], 44, project);
  const positions = [a, b, neighbor].map(p => ({
    x: project(p).x + result.get(p.id).x, y: project(p).y + result.get(p.id).y,
  }));
  positions.forEach((p, i) => positions.slice(i + 1).forEach(q => {
    assert.ok(Math.hypot(p.x - q.x, p.y - q.y) >= 43.99);
  }));
  assert.equal(result.get("c").moved, false);
  assert.deepEqual(result, offsets([neighbor, b, a], 44, project));
});
