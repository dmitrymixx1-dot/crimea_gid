/* leaflet-map.js — обёртка над Leaflet для опционального интерактивного слоя.
 *
 * Принципы (в соответствии с архитектурой проекта):
 * 1. По умолчанию пользователь видит существующую SVG-схему — она работает
 *    без сети и без каких-либо внешних запросов.
 * 2. Интерактивный слой включается пользователем явно (кнопка «Спутник/карта»);
 *    без этого Leaflet не инициализируется и не тянет тайлы.
 * 3. Загрузка Leaflet — динамическая (через <script>/<link> в момент
 *    переключения), чтобы не добавлять ~160 Кб в холодную загрузку.
 * 4. Ошибка загрузки (сеть есть, но недоступны тайлы или CDN не нужен —
 *    Leaflet у нас локально, но тайлы внешние) не роняет страницу:
 *    кнопка отключается, показывается тост.
 *
 * Экспортируется в глобал `LeafletMap` (UMD), как другие модули проекта.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    /* Node-окружение: тесты. Leaflet там нет, отдаём хелперы. */
    module.exports = factory(null, require("./map-layout.js"));
  } else {
    root.LeafletMap = factory(root.L, root.MapLayout);
  }
})(typeof self !== "undefined" ? self : this, function (L, MapLayout) {
  "use strict";

  /* Центр и дефолтный зум Крыма. */
  var CENTER = [45.05, 34.25];
  var ZOOM_DEFAULT = 8;
  var ZOOM_MIN = 7;
  var ZOOM_MAX = 14;

  var STYLE_COLORS = {
    beach: "#f59e0b", castle: "#8b5cf6", palace: "#6366f1", winery: "#991b1b",
    nature: "#15803d", park: "#4d7c0f", city: "#0284c7", spa: "#0f766e",
    food: "#c2410c", museum: "#7e22ce", active: "#b45309", factory: "#db2777",
  };

  /* Динамически подключает Leaflet CSS/JS один раз. */
  var _loader = null;
  function loadLeaflet() {
    if (typeof L !== "undefined" && L && L.map) return Promise.resolve(L);
    if (_loader) return _loader;
    _loader = new Promise(function (resolve, reject) {
      /* CSS */
      if (!document.querySelector('link[href*="leaflet.css"]')) {
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "/static/vendor/leaflet.css";
        document.head.appendChild(link);
      }
      /* JS */
      var existing = document.querySelector('script[src*="leaflet.js"]');
      if (existing) {
        existing.addEventListener("load", function () { resolve(window.L); });
        existing.addEventListener("error", reject);
        return;
      }
      var s = document.createElement("script");
      s.src = "/static/vendor/leaflet.js";
      s.onload = function () { resolve(window.L); };
      s.onerror = function () { reject(new Error("Leaflet не загрузился")); };
      document.head.appendChild(s);
    });
    return _loader;
  }

  /* Собирает конфиг для divIcon одного цвета с эмодзи внутри —
     в стиле SVG-маркеров. Конфиг — простой объект, чтобы его можно
     было тестировать в Node без Leaflet; в мапере передаём в L.divIcon(). */
  function iconConfig(type, emoji) {
    var color = STYLE_COLORS[type] || "#64748b";
    return {
      className: "lm-marker",
      html: '<div class="lm-pin" style="background:' + color + '">' +
            '<span class="lm-emoji">' + emoji + '</span></div>',
      iconSize: [28, 36],
      iconAnchor: [14, 34],
      popupAnchor: [0, -32],
    };
  }

  function buildIcon(type, emoji) {
    if (!L) return iconConfig(type, emoji);
    return L.divIcon(iconConfig(type, emoji));
  }

  /* Создание/обновление карты.
   *
   * container — DOM-элемент, в который рисуем.
   * items     — массив достопримечательностей (a.lat, a.lng, a.name, a.type, ...).
   * onSelect  — колбэк (id) при клике на маркер (открывает модалку).
   * options   — { showPlan: bool, planStops: [{id,lat,lng,name}]}
   */
  function createOrUpdate(container, items, onSelect, options) {
    options = options || {};
    return loadLeaflet().then(function (Leaflet) {
      L = Leaflet;
      // Ленивый загрузчик мог завершиться уже после ухода с экрана.
      if (!container.isConnected) return null;
      if (!container._lm) {
        /* Вырубаем атрибуцию по умолчанию частично — оставляем обязательную
         * строчку OpenStreetMap, но убираем кричащий баннер Leaflet,
         * так как ссылка на него уже есть в подвале карты. */
        var map = L.map(container, {
          center: CENTER,
          zoom: ZOOM_DEFAULT,
          minZoom: ZOOM_MIN,
          maxZoom: ZOOM_MAX,
          zoomControl: true,
          // Фильтр/роут может удалить контейнер во время zoom-перехода.
          // Без анимации Leaflet не оставляет таймер к уже удалённой карте.
          zoomAnimation: false,
          attributionControl: true,
        });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: ZOOM_MAX,
        }).addTo(map);
        container._lm = {
          map: map,
          markers: L.featureGroup().addTo(map),
          planLayer: L.layerGroup().addTo(map),
        };
        /* L.map ломает размеры, если контейнер был скрыт: invalidateSize
         * на следующий тик после появления. */
        setTimeout(function () { map.invalidateSize(); }, 0);
      }
      var state = container._lm;

      // Убираем прежний обработчик при фильтрации/переключении плана.
      if (state.reposition) state.map.off("zoomend", state.reposition);
      state.map.invalidateSize();
      state.markers.clearLayers();
      state.planLayer.clearLayers();
      var stops = options.showPlan && Array.isArray(options.planStops) ? options.planStops : [];
      var points = items.concat(stops);
      var offsets;
      function layout() {
        offsets = MapLayout.offsets(points, 44, function (a) {
          return state.map.latLngToLayerPoint([a.lat, a.lng]);
        });
      }
      // Границы — по настоящим координатам, включая план вне фильтра.
      if (points.length) {
        state.map.fitBounds(L.latLngBounds(points.map(function (a) { return [a.lat, a.lng]; })).pad(0.2),
          { maxZoom: 11, animate: false });
      }
      layout();
      var displaced = [];
      function displayPoint(a) {
        var offset = offsets.get(a.id);
        var point = state.map.latLngToLayerPoint([a.lat, a.lng]);
        return state.map.layerPointToLatLng(L.point(point.x + offset.x, point.y + offset.y));
      }
      items.forEach(function (a) {
        var meta = (options.typesMeta && options.typesMeta[a.type]) || { emoji: "📍" };
        var marker = L.marker(displayPoint(a), {
          icon: buildIcon(a.type, meta.emoji), title: a.name, alt: a.name,
        }).on("click", function () { if (onSelect) onSelect(a.id); });
        var line = null;
        if (offsets.get(a.id).moved) {
          line = L.polyline([[a.lat, a.lng], displayPoint(a)], {
            color: "#64748b", weight: 1.5, interactive: false,
          }).addTo(state.markers);
        }
        state.markers.addLayer(marker);
        displaced.push({ item: a, marker: marker, line: line });
      });

      /* Маршрут идёт по настоящим координатам; номера — над своими
         маркерами. Остановка открывается и когда её нет в фильтре. */
      if (stops.length > 1) {
        L.polyline(stops.map(function (s) { return [s.lat, s.lng]; }), {
          color: "#f5a524", weight: 3, opacity: 0.85, dashArray: "7 5", interactive: false,
        }).addTo(state.planLayer);
      }
      stops.forEach(function (s, i) {
        var marker = L.marker(displayPoint(s), {
          icon: L.divIcon({
            className: "lm-plan-num",
            html: '<div class="lm-num-pin">' + (i + 1) + "</div>",
            iconSize: [24, 28], iconAnchor: [12, 56],
          }),
          title: s.name, alt: s.name,
        }).on("click", function () { if (onSelect) onSelect(s.id); })
          .addTo(state.planLayer);
        displaced.push({ item: s, marker: marker });
      });
      // Смещения остаются пиксельными при любом масштабе, не становятся
      // ложными географическими координатами после zoom.
      state.reposition = function () {
        layout();
        displaced.forEach(function (entry) {
          var point = displayPoint(entry.item);
          entry.marker.setLatLng(point);
          if (entry.line) entry.line.setLatLngs([[entry.item.lat, entry.item.lng], point]);
        });
      };
      state.map.on("zoomend", state.reposition);
      return state.map;
    });
  }

  function destroy(container) {
    if (container && container._lm) {
      try { container._lm.map.remove(); } catch (e) { /* ignore */ }
      container._lm = null;
    }
  }

  return {
    CENTER: CENTER,
    ZOOM_DEFAULT: ZOOM_DEFAULT,
    ZOOM_MIN: ZOOM_MIN,
    ZOOM_MAX: ZOOM_MAX,
    loadLeaflet: loadLeaflet,
    createOrUpdate: createOrUpdate,
    destroy: destroy,
    /* exported for tests */
    _iconConfig: iconConfig,
    _buildIcon: buildIcon,
    _STYLE_COLORS: STYLE_COLORS,
  };
});
