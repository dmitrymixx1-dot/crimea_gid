/* Общая раскладка совпавших точек: координаты каталога не меняем.
   Смещение — только в единицах экрана (SVG / пикселях Leaflet).
   Порядок по id сохраняет расположение при сортировке и переводе. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.MapLayout = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function offsets(items, spacing, project) {
    spacing = spacing || 44;
    var groups = new Map();
    var result = new Map();
    items.forEach(function (a) {
      var key = a.lat + "," + a.lng;
      if (!groups.has(key)) groups.set(key, new Map());
      groups.get(key).set(a.id, a);
    });
    // Не сдвигаем дубли поверх соседних (несовпавших) точек.
    var occupied = project ? items.map(project) : [];
    Array.from(groups.keys()).sort().forEach(function (key) {
      var group = groups.get(key);
      var ids = Array.from(group.keys()).sort();
      var n = ids.length;
      // Хорда между соседями не меньше spacing и в группе из 3+ мест.
      var radius = n > 1 ? spacing / (2 * Math.sin(Math.PI / n)) : 0;
      ids.forEach(function (id, i) {
        var angle = Math.PI + i * 2 * Math.PI / n;
        var offset = { x: radius * Math.cos(angle), y: radius * Math.sin(angle), moved: n > 1 };
        if (project && n > 1) {
          var anchor = project(group.get(id));
          var free = function (p) {
            return occupied.every(function (q) {
              return Math.hypot(anchor.x + p.x - q.x, anchor.y + p.y - q.y) >= spacing;
            });
          };
          // Сначала ближайшее кольцо, затем наружу. Линия к якорю
          // явно показывает, что это выноска, а не новый адрес.
          var ring = 1;
          while (!free(offset)) {
            var found = false;
            for (var j = 0; j < 16 * ring; j++) {
              var theta = Math.PI + j * 2 * Math.PI / (16 * ring);
              offset.x = spacing * ring * Math.cos(theta);
              offset.y = spacing * ring * Math.sin(theta);
              if (free(offset)) { found = true; break; }
            }
            if (found) break;
            ring++;
          }
          occupied.push({ x: anchor.x + offset.x, y: anchor.y + offset.y });
        }
        result.set(id, offset);
      });
    });
    return result;
  }

  return { offsets: offsets };
});
