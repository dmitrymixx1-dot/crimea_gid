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
    module.exports = factory(null);
  } else {
    root.LeafletMap = factory(root.L);
  }
})(typeof self !== "undefined" ? self : this, function (L) {
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
          attributionControl: true,
        });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: ZOOM_MAX,
        }).addTo(map);
        container._lm = {
          map: map,
          markers: L.layerGroup().addTo(map),
          planLayer: L.layerGroup().addTo(map),
        };
        /* L.map ломает размеры, если контейнер был скрыт: invalidateSize
         * на следующий тик после появления. */
        setTimeout(function () { map.invalidateSize(); }, 0);
      }
      var state = container._lm;

      /* --- маркеры --- */
      state.markers.clearLayers();
      items.forEach(function (a) {
        var meta = (options.typesMeta && options.typesMeta[a.type]) || { emoji: "📍" };
        var marker = L.marker([a.lat, a.lng], { icon: buildIcon(a.type, meta.emoji), title: a.name })
          .on("click", function () { if (onSelect) onSelect(a.id); })
          .bindPopup("<b>" + a.name + "</b><br><small>" + (a.region || "") + "</small>");
        state.markers.addLayer(marker);
      });

      /* --- план маршрута --- */
      state.planLayer.clearLayers();
      if (options.showPlan && Array.isArray(options.planStops) && options.planStops.length > 1) {
        var latlngs = options.planStops.map(function (s) { return [s.lat, s.lng]; });
        L.polyline(latlngs, { color: "#f5a524", weight: 3, opacity: 0.85, dashArray: "7 5" })
          .addTo(state.planLayer);
        options.planStops.forEach(function (s, i) {
          L.marker([s.lat, s.lng], {
            icon: L.divIcon({
              className: "lm-plan-num",
              html: '<div class="lm-num-pin">' + (i + 1) + "</div>",
              iconSize: [24, 28],
              iconAnchor: [12, 26],
            }),
            title: s.name,
            interactive: true,
          }).on("click", function () { if (onSelect) onSelect(s.id); })
            .addTo(state.planLayer);
        });
      }

      /* Подгоняем видимую область под текущие точки, если есть что показывать. */
      var markerBounds = state.markers.getLayers().length
        ? state.markers.getBounds()
        : null;
      if (markerBounds && markerBounds.isValid()) {
        state.map.fitBounds(markerBounds.pad(0.2), { maxZoom: 11, animate: false });
      }
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
