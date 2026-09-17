/* ============ Крым.Гид — SPA ============ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const view = $("#view");

const TOPIC_LABELS = {
  beach: "🏖️ Пляжи", weather: "🌤️ Погода", transport: "🚗 Транспорт",
  events: "🎉 События", food: "🍷 Гастро", safety: " Безопасность",
  history: "🏛️ История",
};

/* Экранирование для атрибутов/текста, которые собираем в шаблонах. */
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* Температура в русской записи: +23°, ноль и минус без «+»; null — «—». */
const fmtTemp = t => (t === null || t === undefined)
  ? "—"
  : `${Number(t) > 0 ? "+" : ""}${Math.round(Number(t))}°`;

/* Авария загрузки картинки: inline-обработчики запрещены CSP, поэтому
   одна делегированная пойма (capture) смотрит на data-img-fallback. */
document.addEventListener("error", e => {
  const el = e.target;
  if (!el || el.tagName !== "IMG") return;
  const mode = el.dataset.imgFallback;
  if (mode === "remove") el.remove();
  else if (mode === "hide") el.style.display = "none";
  else if (mode === "soft") el.style.background = "var(--sea-soft)";
}, true);

const state = {
  meta: { tags: {}, types: {} },
  attractions: [],
  areas: [],
  quiz: null,
  news: null,
  f: { q: "", area: "", tag: "", sort: "rating", open: false },
  q: { step: 0, answers: {} },
  quizResult: null,
  newsView: { topic: "all", onlyCrimea: true, q: "" },
  newsLoading: false,
  favs: new Set(),
  planAutoDone: false,
  weather: null,
  sea: null,
  mapShowPlan: false,
  // Порционный показ каталога: текущая подборка и сколько карточек
  // из неё уже нарисовано (см. static/catalog-page.js).
  catItems: [],
  catShown: 0,
};

// Наблюдатель догрузки живёт вне state: это ресурс DOM, а не данные.
let catObserver = null;

/* ---------------- favorites ---------------- */
function loadFavs() {
  try { state.favs = new Set(JSON.parse(localStorage.getItem("crimea_favs") || "[]")); }
  catch { state.favs = new Set(); }
}
function saveFavs() {
  try { localStorage.setItem("crimea_favs", JSON.stringify([...state.favs])); } catch (e) {}
}
function toggleFav(id) {
  if (state.favs.has(id)) state.favs.delete(id);
  else state.favs.add(id);
  saveFavs();
  route();
}

/* ---------------- utils ---------------- */
async function api(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function toast(msg, ms = 3200) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const hm = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === new Date().toDateString()) return `сегодня, ${hm}`;
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function tagLabel(t) { return state.meta.tags[t] || t; }

function budgetIcons(b) { return "₽".repeat(b) + `<span class="muted">${"₽".repeat(3 - b)}</span>`; }

/* Осмысленный alt категорийной картинки: что изображено, без дубля
   названия места (оно и так рядом в заголовке карточки). */
function typeAlt(meta) { return `Иллюстрация категории «${meta.label || meta.img}»`; }

function favBtn(id) {
  return `<button class="fav-btn ${state.favs.has(id) ? "on" : ""}" data-fav="${id}"
    aria-pressed="${state.favs.has(id)}"
    title="${state.favs.has(id) ? "Убрать из избранного" : "В избранное"}"
    aria-label="${state.favs.has(id) ? "Убрать из избранного" : "В избранное"}">♥</button>`;
}

/* ---------------- news ---------------- */
async function loadNews(refresh = false) {
  state.news = await api(`/api/news?limit=50${refresh ? "&refresh=1" : ""}`);
  updateNetBadge();
}

function updateNetBadge() {
  const b = $("#net-badge");
  if (!state.news) return;
  if (state.news.online) {
    b.className = "badge badge-ok badge-dot";
    b.textContent = "live";
    b.title = `Источники на связи. Обновлено: ${fmtTime(state.news.updated_at)}`;
  } else {
    b.className = "badge badge-warn badge-dot";
    b.textContent = "офлайн";
    b.title = "RSS-ленты недоступны из вашей сети — показываем кэш";
  }
}

/* ---------------- cards ---------------- */
function attractionCard(a) {
  const meta = state.meta.types[a.type] || { emoji: "📍", img: "cat_nature.jpg", label: a.type };
  const chips = a.tags.slice(0, 3)
    .map(t => `<span class="chip">${tagLabel(t)}</span>`).join("");
  const openLabel = OpenNow.label(a);
  return `
    <article class="card" data-id="${a.id}">
      <div class="card-img">
        <img src="/static/img/${meta.img}" alt="${esc(typeAlt(meta))}" loading="lazy"
             decoding="async" data-img-fallback="remove" />
        ${favBtn(a.id)}
        <div class="emoji" aria-hidden="true">${meta.emoji}</div>
      </div>
      <div class="card-body">
        <h3 class="card-title"><a href="#/place/${a.id}">${esc(a.name)}</a></h3>
        <div class="card-region">📍 ${esc(a.region)}</div>
        <p class="card-desc">${esc(a.description)}</p>
        <div class="card-chips">${chips}</div>
        <div class="card-meta">
          <span><span class="star" aria-hidden="true">★</span> <b>${a.rating.toFixed(1)}</b></span>
          <span>${budgetIcons(a.budget)}</span>
          <span>⏱ ${a.duration_h} ч</span>
        </div>
        ${openLabel ? `<div class="open-now">${esc(openLabel)}</div>` : ""}
      </div>
    </article>`;
}

function newsItemHTML(it) {
  const topics = (it.topics || [])
    .map(t => `<span class="chip ${t === "safety" ? "chip-sun" : ""}">${TOPIC_LABELS[t] || t}</span>`)
    .join("");
  return `
    <div class="news-item">
      <div class="news-left">
        <span class="source-badge">${esc(it.source)}</span>
        <span class="news-time">${fmtTime(it.published)}</span>
      </div>
      <div class="news-body">
        <h3 class="news-title"><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
        ${it.summary ? `<p class="news-summary">${esc(it.summary)}</p>` : ""}
        ${topics ? `<div class="news-topics">${topics}</div>` : ""}
      </div>
    </div>`;
}

/* ---------------- sea ---------------- */
/* Купальный индекс приходит с сервера готовым вердиктом: пороги живут
   в app/services/marine.py, фронт их не дублирует (в отличие от
   «открыто сейчас», где решение зависит от часов устройства). */
function seaStrip() {
  const s = state.sea;
  if (!s) return "";
  const points = (s.points || []).filter(p => p.available);
  if (!points.length) {
    return `
    <section class="section sea-strip">
      <div class="section-head"><h2>🌊 Море и купание</h2></div>
      <p class="muted" style="margin:0">Данных о воде сейчас нет — морская модель недоступна. Попробуйте позже.</p>
    </section>`;
  }
  const best = s.warmest;
  return `
    <section class="section sea-strip">
      <div class="section-head">
        <h2>🌊 Море и купание</h2>
        <span class="sub">Open-Meteo Marine · вода и волна · обновление раз в 3 часа</span>
      </div>
      ${best ? `<p class="sea-best">Самая тёплая вода — <b>${esc(best.name)}</b>,
        ${fmtTemp(best.temp)}</p>` : ""}
      <div class="weather-grid">
        ${points.map(p => `
          <div class="w-city sea-city">
            <div class="w-name">${esc(p.name)}</div>
            <div class="w-main">🌊 <b>${fmtTemp(p.water_temp)}</b></div>
            <div class="sea-wave">${waveText(p)}</div>
            <div class="sea-verdict sea-${esc(p.verdict.code)}">
              ${p.verdict.emoji} ${esc(p.verdict.label)}
            </div>
          </div>`).join("")}
      </div>
      <p class="muted sea-note">Температуру поверхности воды и волну считает
        морская модель: у берега вода может быть прохладнее, на мелководье — теплее.
        Купайтесь на оборудованных пляжах.</p>
    </section>`;
}

/* «волна 0,3 м · лёгкая рябь»; если модель отдала только температуру —
   волну не выдумываем. */
function waveText(p) {
  if (p.wave_height === null || p.wave_height === undefined) return "волна: нет данных";
  const m = String(p.wave_height).replace(".", ",");
  return `волна ${m} м${p.wave_label ? ` · ${esc(p.wave_label)}` : ""}`;
}

/* ---------------- home ---------------- */
/* Почасовой прогноз: окно считает Hourly.next по крымскому времени —
   ответ API живёт в кэше до часа, и «сейчас» в нём стареет. <details>
   даёт раскрытие без JS-обработчиков (CSP: только внешние скрипты)
   и работает с клавиатуры. */
function hourlyStrip(city) {
  if (typeof Hourly === "undefined" || !Array.isArray(city.hourly)) return "";
  const hours = Hourly.next(city.hourly, new Date());
  if (!hours.length) return "";
  return `
    <details class="w-hours">
      <summary>По часам</summary>
      <div class="w-hourly">
        ${hours.map(h => `
          <span class="w-hour${h.label === "сейчас" ? " w-hour-now" : ""}">
            <span class="w-hour-t">${esc(h.label)}</span>
            <span class="w-hour-v">${esc(h.emoji)} ${fmtTemp(h.temp)}</span>
            ${h.precipLabel ? `<span class="w-hour-p">${esc(h.precipLabel)}</span>` : ""}
          </span>`).join("")}
      </div>
      <p class="w-hourly-note">Температура и вероятность осадков по Open-Meteo.</p>
    </details>`;
}

function weatherStrip() {
  const w = state.weather;
  if (!w) return "";
  const cities = (w.cities || []).filter(c => c.available);
  if (!cities.length) {
    return `
    <section class="section weather-strip">
      <div class="section-head"><h2>🌤 Погода на курортах</h2></div>
      <p class="muted" style="margin:0">Погода сейчас недоступна — попробуйте позже.</p>
    </section>`;
  }
  return `
    <section class="section weather-strip">
      <div class="section-head">
        <h2>🌤 Погода на курортах</h2>
        <span class="sub">Open-Meteo · обновление раз в час</span>
      </div>
      <div class="weather-grid">
        ${cities.map(c => `
          <div class="w-city" title="${c.current.label}, ветер ${c.current.wind} км/ч">
            <div class="w-name">${c.name}</div>
            <div class="w-main">${c.current.emoji} <b>${fmtTemp(c.current.temp)}</b></div>
            <div class="w-forecast">
              ${c.forecast.slice(1, 4).map(f =>
                `<span class="w-day" title="${f.day}">${f.day} ${f.emoji} ${fmtTemp(f.max)}</span>`).join("")}
            </div>
            ${hourlyStrip(c)}
          </div>`).join("")}
      </div>
    </section>`;
}

function renderHome() {
  const top = [...state.attractions].sort((a, b) => b.rating - a.rating).slice(0, 4);
  const favs = state.attractions.filter(a => state.favs.has(a.id));
  const n = state.news;
  const teaser = n
    ? n.items.filter(x => x.crimea_score > 0).slice(0, 3)
    : [];
  const cats = [
    ["beach", "cat_beach.jpg"], ["history", "cat_history.jpg"], ["nature", "cat_nature.jpg"],
    ["wine", "cat_wine.jpg"], ["family", "cat_family.jpg"], ["active", "cat_active.jpg"],
  ];
  view.innerHTML = `
    <section class="hero">
      <img src="/static/img/hero.jpg" alt="Южный берег Крыма на закате"
           fetchpriority="high" decoding="async" data-img-fallback="hide" />
      <div class="hero-content">
        <h1>Крым подскажет,<br />куда вам сходить</h1>
        <p>Пройдите квиз за минуту — соберём маршрут под ваши интересы.
           А ещё — каталог проверенных мест и живая лента новостей полуострова.</p>
        <div class="hero-actions">
          <a class="btn btn-sun" href="#/quiz">🎯 Пройти квиз</a>
          <a class="btn btn-ghost" href="#/catalog">Смотреть каталог</a>
          <a class="btn btn-ghost" href="#/map">🗺 Карта</a>
        </div>
        <div class="hero-stats">
          <span class="hero-stat">📍 ${state.attractions.length} мест</span>
          <span class="hero-stat">❓ ${state.quiz ? state.quiz.questions.length : 7} вопросов</span>
          <span class="hero-stat">📰 ${n ? n.sources.length : 5} источников новостей</span>
        </div>
      </div>
    </section>

    ${weatherStrip()}
    ${seaStrip()}
    <section class="section">
      <div class="section-head">
        <h2>Ваш профиль отдыха</h2>
        <span class="sub">Выберите настроение — откроется каталог по теме</span>
      </div>
      <div class="grid">
        ${cats.map(([t, img]) => `
          <a class="card cat-tile" href="#/catalog?tag=${t}">
            <div class="card-img"><img src="/static/img/${img}"
              alt="Иллюстрация категории «${esc(tagLabel(t))}»"
              loading="lazy" decoding="async" data-img-fallback="remove"/></div>
            <div class="card-body">
              <h3 class="card-title">${tagLabel(t)}</h3>
              <div class="card-region">места с тегом «${t}»</div>
            </div>
          </a>`).join("")}
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Выбранное путешественников</h2>
        <a class="btn btn-outline btn-sm" href="#/catalog">Весь каталог →</a>
      </div>
      <div class="grid">${top.map(attractionCard).join("")}</div>
    </section>

    ${n ? `
    <section class="section">
      <div class="section-head">
        <h2>Свежее с полуострова</h2>
        <a class="btn btn-outline btn-sm" href="#/news">Все новости →</a>
      </div>
      ${teaser.length ? teaser.map(newsItemHTML).join("") : `<div class="empty"><div class="big">📭</div>Крымских новостей пока нет — загляните позже.</div>`}
    </section>` : ""}
  ${favs.length ? `
    <section class="section">
      <div class="section-head">
        <h2>❤ В избранном</h2>
        <span style="display:flex;gap:10px;align-items:center">
          <span class="sub">${favs.length} ${plural(favs.length, ["место", "места", "мест"])} — сохранено в вашем браузере</span>
          <button class="btn btn-outline btn-sm" id="fav-share"
            title="Скопировать ссылку на ваше избранное">🔗 Ссылка на избранное</button>
        </span>
      </div>
      <div class="grid">${favs.map(attractionCard).join("")}</div>
    </section>` : ""}
  `;
  bindCards();
  $("#fav-share")?.addEventListener("click", copyFavsLink);
}

/* Счётчик по-русски: 1 место, 2 места, 5 мест. */
function plural(n, forms) {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return forms[0];
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
  return forms[2];
}

/* Ссылка на избранное (#/favs?f=id1,id2): получатель за один тап
   добавляет эти места к своему избранному. Ссылка только добавляет —
   своё избранное она не трогает. */
function copyFavsLink() {
  const url = FavsLink.favsUrl([...state.favs], location.origin, location.pathname);
  if (!url) { toast("В избранном пока пусто"); return; }
  const done = () => toast("🔗 Ссылка на избранное скопирована");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done, () => fallbackCopy(url, done));
  else fallbackCopy(url, done);
}

/* Вхождение по ссылке #/favs?f=…: добавляем узнаваемые id к своему
   избранному и уводим на главную, где оно и отображается. */
function importFavsFromQuery(query) {
  const known = state.attractions.map(a => a.id);
  const ids = FavsLink.parseFavsQuery(query, known);
  const added = ids.filter(id => !state.favs.has(id));
  if (added.length) {
    for (const id of added) state.favs.add(id);
    saveFavs();
  }
  history.replaceState(null, "", location.pathname + "#/");
  if (added.length) {
    toast(`❤ Из ссылки добавлено в избранное: ${added.length} ${plural(added.length, ["место", "места", "мест"])}`);
  } else if (ids.length) {
    toast("Эти места уже в вашем избранном");
  }
  route();
}

/* ---------------- catalog ---------------- */
/* Фильтры каталога живут в URL (#/catalog?tag=&area=&q=&sort=): подборку
   можно скопировать и открыть у другого человека. URL — источник правды
   при входе по ссылке; дальше состояние держим в state.f и зеркалим
   его в адрес через replaceState (без спама в истории). */
function syncCatalogUrl() {
  const { path } = hashParts();
  if (path !== "catalog") return;  // не трогаем #/place/… и другие маршруты
  const q = CatalogLink.buildCatalogQuery(state.f);
  const target = "#/catalog" + (q ? "?" + q : "");
  if (location.hash !== target) {
    history.replaceState(null, "", location.pathname + target);
  }
}

function copyCatalogLink() {
  const url = CatalogLink.catalogUrl(state.f, location.origin, location.pathname);
  const done = () => toast("🔗 Ссылка на подборку скопирована");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done, () => fallbackCopy(url, done));
  else fallbackCopy(url, done);
}

function renderCatalog(focusTag) {
  const tagBtns = Object.keys(state.meta.tags).map(t => `
    <button class="chip-btn ${state.f.tag === t ? "active" : ""}" data-tag="${t}"
      aria-pressed="${state.f.tag === t}">${tagLabel(t)}</button>`).join("");
  view.innerHTML = `
    <div class="section">
      <div class="section-head"><h2>Каталог мест</h2>
        <span style="display:flex;gap:10px;align-items:center">
          <span class="count-note" id="cat-count"></span>
          <button class="btn btn-outline btn-sm" id="cat-share"
            title="Скопировать ссылку на текущую подборку">🔗 Ссылка на подборку</button>
        </span>
      </div>
      <div class="filters">
        <div class="filter-row">
          <input class="search" id="cat-search" placeholder="Поиск: Ласточкино, вино, пляж…"
            aria-label="Поиск по каталогу" value="${esc(state.f.q)}" />
          <select class="select" id="cat-area" aria-label="Географический район">
            <option value="">Вся география</option>
            ${state.areas.map(a => `<option value="${esc(a)}" ${state.f.area === a ? "selected" : ""}>${esc(a)}</option>`).join("")}
          </select>
          <select class="select" id="cat-sort" title="Сортировка" aria-label="Сортировка">
            <option value="rating" ${state.f.sort === "rating" ? "selected" : ""}>⭐ по рейтингу</option>
            <option value="name" ${state.f.sort === "name" ? "selected" : ""}>А→Я по названию</option>
            <option value="time" ${state.f.sort === "time" ? "selected" : ""}>⏱ по времени</option>
            <option value="budget" ${state.f.sort === "budget" ? "selected" : ""}>₽ по бюджету</option>
          </select>
        </div>
        <div class="filter-row" id="cat-tags">${tagBtns}</div>
        <div class="filter-row">
          <button class="chip-btn ${state.f.open ? "active" : ""}" id="cat-open"
            aria-pressed="${state.f.open}"
            title="Показать то, что работает прямо сейчас (время крымское)">
            🕘 Открыто сейчас</button>
          ${state.f.open ? `<span class="muted open-note">Расписание сезонное — уточняйте на месте</span>` : ""}
        </div>
      </div>
      <div class="grid" id="cat-grid"></div>
      <div class="cat-more" id="cat-more"></div>
    </div>`;
  $("#cat-search").addEventListener("input", e => { state.f.q = e.target.value; renderCatGrid(); syncCatalogUrl(); });
  $("#cat-area").addEventListener("change", e => { state.f.area = e.target.value; renderCatGrid(); syncCatalogUrl(); });
  $("#cat-sort").addEventListener("change", e => { state.f.sort = e.target.value; renderCatGrid(); syncCatalogUrl(); });
  $("#cat-share").addEventListener("click", copyCatalogLink);
  $("#cat-open").addEventListener("click", () => {
    state.f.open = !state.f.open;
    renderCatalog();          // перерисовываем: у кнопки меняется подпись
  });
  $$("#cat-tags .chip-btn").forEach(b => b.addEventListener("click", () => {
    state.f.tag = state.f.tag === b.dataset.tag ? "" : b.dataset.tag;
    renderCatalog(b.dataset.tag);  // перерисовка + новый URL + возврат фокуса
  }));
  renderCatGrid();
  syncCatalogUrl();
  if (focusTag) {
    const chip = $(`#cat-tags .chip-btn[data-tag="${focusTag}"]`);
    if (chip) chip.focus();
  }
}

function renderCatGrid() {
  const grid = $("#cat-grid");
  if (!grid) return;
  const q = state.f.q.toLowerCase();
  let items = state.attractions.filter(a =>
    (!state.f.area || a.area === state.f.area) &&
    (!state.f.tag || a.tags.includes(state.f.tag)) &&
    (!q || a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q)));
  // «Открыто сейчас» прячет только заведомо закрытое: у пляжей и мысов
  // расписания нет, и выбрасывать их было бы враньём (см. open-now.js).
  if (state.f.open) items = OpenNow.filterOpen(items);
  const SORTS = {
    rating: (a, b) => b.rating - a.rating,
    name: (a, b) => a.name.localeCompare(b.name, "ru"),
    time: (a, b) => b.duration_h - a.duration_h,
    budget: (a, b) => a.budget - b.budget,
  };
  items.sort(SORTS[state.f.sort] || SORTS.rating);
  // Новая подборка — показываем с начала: иначе после смены фильтра
  // пользователь видел бы «докрученный» хвост предыдущей выдачи.
  state.catShown = CatalogPage.firstPage(items.length);
  state.catItems = items;
  paintCatGrid();
}

/* Рисует подборку с нуля: смена фильтра, сортировки или входа по ссылке. */
function paintCatGrid() {
  const grid = $("#cat-grid");
  if (!grid) return;
  const items = state.catItems || [];
  if (!items.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="big">🔍</div>Ничего не нашлось. Попробуйте убрать фильтры.</div>`;
    $("#cat-count").textContent = CatalogPage.statusLabel(0, 0);
    setCatMore(0);
    return;
  }
  grid.innerHTML = CatalogPage.visible(items, state.catShown)
    .map(attractionCard).join("");
  updateCatTail(grid);
}

/* Дорисовывает следующую порцию, не трогая уже отрисованные карточки:
   перерендер всей сетки съел бы весь выигрыш и сбрасывал бы фокус. */
function appendCatCards(from) {
  const grid = $("#cat-grid");
  if (!grid) return;
  const items = state.catItems || [];
  const chunk = CatalogPage.visible(items, state.catShown).slice(from);
  if (chunk.length) {
    grid.insertAdjacentHTML("beforeend", chunk.map(attractionCard).join(""));
  }
  updateCatTail(grid);
}

/* Общий хвост обоих путей: счётчик, обработчики карточек, кнопка догрузки. */
function updateCatTail(grid) {
  const total = (state.catItems || []).length;
  $("#cat-count").textContent = CatalogPage.statusLabel(state.catShown, total);
  bindCards(grid);
  setCatMore(CatalogPage.remaining(state.catShown, total));
}

/* Хвост под сеткой: кнопка «Показать ещё» + невидимый «часовой», по
   которому IntersectionObserver догружает порцию при прокрутке.
   Кнопка не декоративная — это доступный путь без скролла и фолбэк
   для браузеров без IntersectionObserver. */
function setCatMore(left) {
  const box = $("#cat-more");
  if (!box) return;
  catObserver?.disconnect();
  if (!left) { box.innerHTML = ""; return; }
  const step = Math.min(left, CatalogPage.PAGE);
  box.innerHTML = `
    <button class="btn btn-outline" id="cat-more-btn">
      Показать ещё ${step} из ${left}
    </button>
    <div id="cat-sentinel" aria-hidden="true"></div>`;
  $("#cat-more-btn").addEventListener("click", showMoreCards);
  const sentinel = $("#cat-sentinel");
  if (typeof IntersectionObserver === "undefined" || !sentinel) return;
  catObserver = new IntersectionObserver(entries => {
    if (entries.some(e => e.isIntersecting)) showMoreCards();
  }, { rootMargin: "400px" });   // догружаем до того, как упрёмся в край
  catObserver.observe(sentinel);
}

function showMoreCards() {
  const total = (state.catItems || []).length;
  if (!CatalogPage.hasMore(state.catShown, total)) return;
  const from = state.catShown;
  state.catShown = CatalogPage.growShown(state.catShown, total);
  appendCatCards(from);
  // Фокус был на кнопке, которую мы только что перерисовали: вернём его,
  // иначе клавиатурный пользователь после догрузки окажется в начале.
  if (document.activeElement === document.body) $("#cat-more-btn")?.focus();
}

/* ---------------- quiz ---------------- */
function renderQuiz() {
  if (state.quizResult) return renderQuizResult();
  const qs = state.quiz.questions;
  const idx = state.q.step;
  const q = qs[idx];
  const ans = state.q.answers[q.id];
  const isMulti = q.type === "multi";
  const options = q.options.map(o => {
    const sel = isMulti ? (ans || []).includes(o.id) : ans === o.id;
    return `
      <button class="option ${sel ? "selected" : ""}" data-opt="${o.id}">
        <span class="o-emoji">${o.emoji}</span>
        <span><span class="o-label">${o.label}</span>
        ${o.hint ? `<div class="o-hint">${o.hint}</div>` : ""}</span>
      </button>`;
  }).join("");
  const pct = Math.round((idx / qs.length) * 100);
  view.innerHTML = `
    <div class="quiz-shell">
      <div class="section-head" style="margin-bottom:0"><h2>Квиз</h2>
        <span class="sub">${q.subtitle || ""}</span></div>
      <div class="progress"><div style="width:${pct}%"></div></div>
      <div class="quiz-card">
        <div class="quiz-emoji">${q.emoji}</div>
        <h2>${q.title}</h2>
        <div class="options">${options}</div>
        ${isMulti ? `<div class="max-note">Выберите до ${q.max} — можно менять выбор</div>` : ""}
        <div class="quiz-nav">
          <button class="btn btn-outline btn-sm" id="q-back" ${idx === 0 ? "disabled" : ""}>← Назад</button>
          <span class="quiz-step">${idx + 1} / ${qs.length}</span>
          ${isMulti ? `<button class="btn btn-primary btn-sm" id="q-next" ${!(ans || []).length ? "disabled" : ""}>Далее →</button>` : ""}
        </div>
      </div>
    </div>`;
  $$(".option").forEach(b => b.addEventListener("click", () => {
    const id = b.dataset.opt;
    if (isMulti) {
      const cur = new Set(ans || []);
      if (cur.has(id)) cur.delete(id);
      else if (cur.size >= q.max) { toast(`Максимум ${q.max} варианта`); return; }
      else cur.add(id);
      state.q.answers[q.id] = [...cur];
    } else {
      state.q.answers[q.id] = id;
      setTimeout(() => { state.q.step++; renderQuiz(); }, 180);
      return;
    }
    renderQuiz();
  }));
  const back = $("#q-back"), next = $("#q-next");
  if (back) back.addEventListener("click", () => { state.q.step--; renderQuiz(); });
  if (next) next.addEventListener("click", submitQuiz);
}

async function submitQuiz() {
  const btn = $("#q-next");
  if (btn) { btn.disabled = true; btn.textContent = "Считаем…"; }
  try {
    state.quizResult = await api("/api/quiz/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.q.answers),
    });
    location.hash = "#/quiz";
    renderQuiz();
  } catch (e) {
    toast("Не удалось посчитать рекомендации");
    if (btn) { btn.disabled = false; btn.textContent = "Далее →"; }
  }
}

const SLOT_META = {
  morning: { icon: "⛅", label: "утро" },
  afternoon: { icon: "🌤", label: "день" },
  evening: { icon: "🌆", label: "вечер" },
  full: { icon: "🗓", label: "целый день" },
};

function dayCard(day) {
  const tags = (day.tags || []).map(t => tagLabel(t)).join(" · ");
  return `
    <div class="day-card">
      <div class="day-head">
        <span class="day-num">День ${day.day}</span>
        <span class="day-area">${day.area_label}</span>
        ${tags ? `<span class="day-tags muted">${tags}</span>` : ""}
      </div>
      ${day.stops.map(s => `
        <div class="stop" data-id="${s.id}">
          <span class="slot">${SLOT_META[s.slot]?.icon || "·"} ${SLOT_META[s.slot]?.label || s.slot}</span>
          <span class="stop-name"><a href="#/place/${s.id}">${s.type_meta.emoji} ${esc(s.name)}</a></span>
          <span class="muted stop-h">⏱ ${s.duration_h} ч</span>
        </div>`).join("")}
    </div>`;
}

function buildPlanLink() {
  const s = PlanLink.buildPlanString(state.quizResult.answers);
  return location.origin + location.pathname + "#/quiz?plan=" + encodeURIComponent(s);
}

async function autoEvaluatePlan(plan) {
  state.q.answers = plan;
  view.innerHTML = `<div class="empty" style="margin-top:40px"><div class="big">🧮</div>Собираем ваш план…</div>`;
  try {
    state.quizResult = await api("/api/quiz/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    });
    renderQuizResult();
  } catch (e) {
    state.planAutoDone = false;
    renderQuiz();
  }
}

function copyPlanLink() {
  const url = buildPlanLink();
  const done = () => toast("🔗 Ссылка на ваш план скопирована");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done, () => fallbackCopy(url, done));
  else fallbackCopy(url, done);
}

function planAsText() {
  const r = state.quizResult;
  const lines = [`🌊 Крым.Гид — ${r.profile.emoji} ${r.profile.title}`, ""];
  for (const d of r.itinerary.days) {
    lines.push(`День ${d.day} · ${d.area_label}`);
    for (const s of d.stops) {
      lines.push(`  ${SLOT_META[s.slot].icon} ${SLOT_META[s.slot].label}: ${s.name} (⏱ ${s.duration_h} ч)`);
    }
    lines.push("");
  }
  if (r.itinerary.reserve.length) {
    lines.push("Запас на дождь или «впритык»:");
    r.itinerary.reserve.slice(0, 8).forEach(s => lines.push(`  • ${s.name}`));
  }
  lines.push("", "Собрано в Крым.Гид: " + location.origin + location.pathname);
  return lines.join("\n");
}

function copyPlanText() {
  const done = () => toast("📋 План скопирован текстом");
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(planAsText()).then(done, () => fallbackCopy(planAsText(), done));
  else fallbackCopy(planAsText(), done);
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { toast(text); }
  ta.remove();
}

function renderQuizResult() {
  const r = state.quizResult;
  const ansChips = state.quiz.questions.map(q => {
    const v = r.answers[q.id];
    if (!v) return "";
    const opts = (Array.isArray(v) ? v : [v])
      .map(id => q.options.find(o => o.id === id)?.label)
      .filter(Boolean).join(" · ");
    return `<span class="hero-stat">${q.emoji} ${opts}</span>`;
  }).join("");
  view.innerHTML = `
    <div class="quiz-shell" style="max-width:760px">
      <div class="profile-card">
        <div class="p-emoji">${r.profile.emoji}</div>
        <h2>${r.profile.title}</h2>
        <p>${r.profile.summary}</p>
        <div class="hero-stats" style="margin-top:16px">${ansChips}</div>
      </div>
      <div class="hint-box">${r.transport_hint}</div>
      <div class="section-head">
        <h2 style="font-size:20px">Вам подобрали ${r.count} мест</h2>
        <span class="sub">на ${r.days_hint} день(и), из ${r.all_matched} подходящих</span>
      </div>
      ${r.recommendations.map(a => `
        <div class="rec-row" data-id="${a.id}">
          ${favBtn(a.id)}
          <img class="rec-img" src="/static/img/${a.type_meta.img}"
            alt="${esc(typeAlt(a.type_meta))}" loading="lazy" decoding="async"
            data-img-fallback="soft" />
          <div class="rec-body">
            <h3><a href="#/place/${a.id}">${a.type_meta.emoji} ${esc(a.name)}</a></h3>
            <div class="rec-region">📍 ${esc(a.region)} · ⏱ ${a.duration_h} ч · <span class="star" aria-hidden="true">★</span> ${a.rating.toFixed(1)}</div>
            <div class="rec-reasons">
              ${a.reasons.map(x => `<span class="chip">${esc(x)}</span>`).join("")}
            </div>
          </div>
          <span class="rec-score" title="балл совпадения">${a.score}</span>
        </div>`).join("")}
      ${r.itinerary && r.itinerary.days.length ? `
        <div class="section-head" style="margin-top:26px">
          <h2 style="font-size:20px">🗺 План по дням</h2>
          <span class="sub">районы сгруппированы, чтобы не бегать через весь полуостров</span>
        </div>
        ${r.itinerary.days.map(dayCard).join("")}
        ${r.itinerary.reserve.length ? `
          <div class="section-head" style="margin-top:20px">
            <h3 style="margin:0;font-size:16px">🌧 Запасной вариант (дождь или «впритык»)</h3>
          </div>
          <div class="reserve-chips">
            ${r.itinerary.reserve.map(s => `<button class="chip-btn" data-id="${s.id}">${s.type_meta.emoji} ${s.name}</button>`).join("")}
          </div>` : ""}` : ""}
      ${r.news && r.news.length ? `
        <div class="section-head" style="margin-top:26px">
          <h2 style="font-size:20px">Новости по вашим интересам</h2>
        </div>
        ${r.news.map(newsItemHTML).join("")}` : ""}
      <div style="display:flex;gap:10px;margin-top:26px;flex-wrap:wrap">
        <button class="btn btn-primary" id="q-again">🔄 Пройти заново</button>
        <button class="btn btn-outline" id="plan-copy">🔗 Скопировать ссылку</button>
        <button class="btn btn-outline" id="plan-text">📋 План текстом</button>
        <button class="btn btn-outline" id="plan-print">🖨 Печать</button>
        <a class="btn btn-outline" href="#/catalog">Открыть каталог</a>
      </div>
    </div>`;
  $$(".rec-row").forEach(el => el.addEventListener("click", e => {
    if (e.target.closest("a")) return;  // ссылка на место уходит роутеру
    openModal(el.dataset.id);
  }));
  $$(".stop[data-id]").forEach(el => el.addEventListener("click", e => {
    if (e.target.closest("a")) return;
    openModal(el.dataset.id);
  }));
  $$(".reserve-chips [data-id]").forEach(el =>
    el.addEventListener("click", () => openModal(el.dataset.id)));
  $("#q-again").addEventListener("click", () => {
    state.q = { step: 0, answers: {} };
    state.quizResult = null;
    state.planAutoDone = false;
    history.replaceState(null, "", location.pathname + "#/quiz");
    renderQuiz();
  });
  $("#plan-copy").addEventListener("click", copyPlanLink);
  $("#plan-text").addEventListener("click", copyPlanText);
  $("#plan-print").addEventListener("click", () => { document.body.classList.add("print-plan"); window.print(); });
}

/* ---------------- news ---------------- */
async function renderNews(refresh = false) {
  if (refresh) state.newsLoading = true;
  view.innerHTML = `
    <div class="section">
      <div class="news-head" id="news-head">
        <div>
          <h2 style="margin:0">Новости Крыма</h2>
          <div class="news-status">
            <span id="news-badge" class="badge badge-muted">загружаем…</span>
            <span class="muted" id="news-upd"></span>
          </div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <div class="filter-row">
            <button class="chip-btn ${state.newsView.onlyCrimea ? "active" : ""}" data-nv="crimea">🌊 Крым</button>
            <button class="chip-btn ${!state.newsView.onlyCrimea ? "active" : ""}" data-nv="all">Все ленты</button>
          </div>
          <input class="search news-search" id="news-search" placeholder="Поиск по новостям…"
            aria-label="Поиск по новостям" value="${esc(state.newsView.q)}" />
          <button class="btn btn-outline btn-sm" id="news-refresh" ${state.newsLoading ? "disabled" : ""}>
            ${state.newsLoading ? "Обновляем…" : "↻ Обновить"}
          </button>
        </div>
      </div>
      <div id="news-offline"></div>
      <div class="filter-row" id="news-topics" style="margin-bottom:16px"></div>
      <div id="news-list"></div>
    </div>`;
  $("#news-refresh").addEventListener("click", () => renderNews(true));
  $("#news-search").addEventListener("input", e => {
    state.newsView.q = e.target.value;
    renderNewsBody();
  });
  $$("#news-head [data-nv]").forEach(b => b.addEventListener("click", () => {
    state.newsView.onlyCrimea = b.dataset.nv === "crimea";
    renderNews();
  }));

  try {
    if (refresh) await loadNews(true);
    else if (!state.news) await loadNews();
  } catch (e) {
    $("#news-list").innerHTML = `<div class="empty"><div class="big">⚠️</div>Не удалось получить новости: ${e.message}</div>`;
    return;
  }
  renderNewsBody();
}

function renderNewsBody() {
  const n = state.news;
  const badge = $("#news-badge");
  if (n.online) {
    badge.className = "badge badge-ok badge-dot";
    badge.textContent = "live";
    const failed = n.failed_sources.length ? ` · упало: ${n.failed_sources.length}` : "";
    $("#news-upd").textContent = `обновлено ${fmtTime(n.updated_at)}${failed}`;
  } else {
    badge.className = "badge badge-warn badge-dot";
    badge.textContent = "офлайн";
    $("#news-upd").textContent = `кэш от ${fmtTime(n.updated_at)}`;
    $("#news-offline").innerHTML = `
      <div class="hint-box" style="margin-bottom:16px">
        📡 RSS-ленты сейчас недоступны из вашей сети — показываем кэшированные материалы.
        Крымская секция в офлайн-режиме — <b>демонстрационные</b> примеры; при подключении сети придут свежие новости.
      </div>`;
  }
  const pool = n.items.filter(x => !state.newsView.onlyCrimea || x.crimea_score > 0);
  const topics = ["all", ...new Set(pool.flatMap(x => x.topics || []))];
  $("#news-topics").innerHTML = topics.map(t => `
    <button class="chip-btn ${state.newsView.topic === t ? "active" : ""}" data-t="${t}">
      ${t === "all" ? "Все темы" : TOPIC_LABELS[t] || t}</button>`).join("");
  $$("#news-topics .chip-btn").forEach(b => b.addEventListener("click", () => {
    state.newsView.topic = b.dataset.t;
    renderNewsBody();
  }));
  const q = state.newsView.q.trim().toLowerCase();
  const items = pool.filter(x =>
    (state.newsView.topic === "all" || (x.topics || []).includes(state.newsView.topic)) &&
    (!q || x.title.toLowerCase().includes(q) || (x.summary || "").toLowerCase().includes(q)));
  $("#news-list").innerHTML = items.length
    ? items.map(newsItemHTML).join("")
    : `<div class="empty"><div class="big">📭</div>${q ? "Ничего не нашлось по запросу." : "По этой теме пока пусто."}</div>`;
}

/* ---------------- modal ---------------- */
/* Focus trap: Tab/Shift+Tab циклятся внутри модалки, фокус входит в неё
   при открытии и возвращается на прежний элемент при закрытии. */
let _modalLastFocus = null;

function modalFocusables() {
  const modal = $("#modal-root .modal");
  if (!modal) return [];
  return $$("a[href], button:not([disabled]), input, select, textarea", modal)
    .filter(el => el.getClientRects().length);
}

function trapModalTab(e) {
  if (e.key !== "Tab") return;
  const els = modalFocusables();
  if (!els.length) return;
  const first = els[0], last = els[els.length - 1];
  const active = document.activeElement;
  const modal = $("#modal-root .modal");
  if (!modal.contains(active)) { e.preventDefault(); first.focus(); return; }
  if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
}

/* Навешивает обработчики на карточки. Идемпотентна: каталог догружается
   порциями и вызывает её повторно поверх уже связанных карточек —
   помечаем обработанные через data-bound, иначе избранное получило бы
   второй listener и переключалось бы дважды (то есть никак). */
function bindCards(root = view) {
  $$("[data-fav]:not([data-bound])", root).forEach(b => {
    b.dataset.bound = "1";
    b.addEventListener("click", e => {
      e.stopPropagation();
      toggleFav(b.dataset.fav);
    });
  });
  // Клик по карточке открывает модалку; клик по внутренней ссылке
  // (#/place/<id>) оставляет переход роутеру — так работает и клавиатура.
  $$(".card[data-id]:not([data-bound]), .rec-row[data-id]:not([data-bound])", root)
    .forEach(el => {
      el.dataset.bound = "1";
      el.addEventListener("click", e => {
        if (e.target.closest("a")) return;
        openModal(el.dataset.id);
      });
    });
}

function openModal(id) {
  const a = state.attractions.find(x => x.id === id);
  if (!a) return;
  const meta = state.meta.types[a.type] || { emoji: "📍", img: "cat_nature.jpg", label: a.type };
  const mapUrl = "https://yandex.ru/maps/?text=" + encodeURIComponent(`Крым, ${a.name}`);
  _modalLastFocus = document.activeElement;
  $("#modal-root").innerHTML = `
    <div class="overlay" id="overlay">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
        <div class="modal-img">
          <img src="/static/img/${meta.img}" alt="${esc(typeAlt(meta))}"
               data-img-fallback="hide" />
          <button class="modal-close" id="m-close" aria-label="Закрыть карточку">✕</button>
        </div>
        <div class="modal-body">
          <h2 id="m-title">${meta.emoji} ${esc(a.name)}</h2>
          <div class="muted">📍 ${esc(a.region)} · ${esc(a.area)}</div>
          <p style="margin-top:12px">${esc(a.description)}</p>
          <div class="facts">
            <div class="fact"><span class="k">Сезон</span>${a.season.map(s => ({ summer: "☀️ лето", spring: "🌸 весна", autumn: "🍂 осень", winter: "❄️ зима" }[s] || s)).join(", ")}</div>
            <div class="fact"><span class="k">Бюджет</span>${budgetIcons(a.budget)} · ${esc(a.price_hint)}</div>
            <div class="fact"><span class="k">Длительность</span>≈ ${a.duration_h} ч</div>
            <div class="fact"><span class="k">Рейтинг</span><span class="star" aria-hidden="true">★</span> ${a.rating.toFixed(1)} / 5</div>
            ${a.hours ? `<div class="fact fact-wide"><span class="k">Часы работы</span>🕘 ${esc(a.hours)}
              ${OpenNow.label(a) ? `<div class="open-now">${esc(OpenNow.label(a))}</div>` : ""}</div>` : ""}
          </div>
          <div class="card-chips">${a.tags.map(t => `<span class="chip">${tagLabel(t)}</span>`).join("")}</div>
          <div class="tip">💡 ${esc(a.tips)}</div>
          <div class="modal-actions">
            <a class="btn btn-primary btn-sm" href="${mapUrl}" target="_blank" rel="noopener">🗺 Открыть на карте</a>
            <button class="btn btn-outline btn-sm" id="m-share">🔗 Поделиться</button>
            <button class="btn btn-outline btn-sm" id="m-close2">Закрыть</button>
          </div>
        </div>
      </div>
    </div>`;
  const close = () => {
    $("#modal-root").innerHTML = ""; document.body.style.overflow = "";
    document.removeEventListener("keydown", trapModalTab, true);
    // Вернуть фокус туда, откуда открыли карточку (клавиатура не теряется).
    if (_modalLastFocus && document.contains(_modalLastFocus)) _modalLastFocus.focus();
    _modalLastFocus = null;
    // Модалка открыта по прямой ссылке #/place/<id> — уходим в каталог,
    // сохраняя фильтры в URL (адрес остаётся источником правды).
    if (hashParts().path.startsWith("place/")) {
      const q = CatalogLink.buildCatalogQuery(state.f);
      history.replaceState(null, "",
        location.pathname + "#/catalog" + (q ? "?" + q : ""));
    }
  };
  state._closeModal = close;
  $("#m-close").addEventListener("click", close);
  $("#m-close2").addEventListener("click", close);
  $("#m-share").addEventListener("click", () => {
    const url = location.origin + location.pathname + "#/place/" + a.id;
    const done = () => toast("🔗 Ссылка на место скопирована");
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done, () => fallbackCopy(url, done));
    else fallbackCopy(url, done);
  });
  $("#overlay").addEventListener("click", e => { if (e.target.id === "overlay") close(); });
  document.body.style.overflow = "hidden";
  document.addEventListener("keydown", trapModalTab, true);
  $("#m-close").focus();  // фокус входит в диалог
}

/* ---------------- map ---------------- */
/* Проекция: равнопромежуточная по lng/lat с поправкой на широту 45°
   (1° долготы ≈ 78.8 км, 1° широты ≈ 111 км) — точки встают географично. */
const MAP = {
  LNG0: 32.40, LAT0: 46.20, LNG1: 36.70, LAT1: 44.25, W: 1000,
  // Упрощённый (low-poly) контур полуострова: [lng, lat], по часовой стрелке,
  // начиная с Перекопа вниз по западному берегу.
  coast: [
    [33.68, 46.15], [33.52, 45.95], [33.30, 45.78], [33.05, 45.68],
    [32.88, 45.66], [32.70, 45.50], [32.58, 45.48], [32.52, 45.44],
    [32.50, 45.40], [32.487, 45.35], [32.545, 45.315], [32.62, 45.28],
    [32.78, 45.235], [32.92, 45.20], [33.00, 45.20], [33.03, 45.40],
    [33.13, 45.18], [33.28, 45.17], [33.36, 45.20], [33.50, 45.12],
    [33.62, 45.06], [33.66, 44.92], [33.55, 44.83], [33.47, 44.70],
    [33.49, 44.62], [33.485, 44.496], [33.60, 44.49], [33.652, 44.427],
    [33.72, 44.41], [33.80, 44.385], [33.90, 44.40], [34.00, 44.405],
    [34.08, 44.415], [34.13, 44.429], [34.16, 44.478], [34.235, 44.500],
    [34.29, 44.535], [34.335, 44.515], [34.42, 44.655], [34.60, 44.72],
    [34.75, 44.78], [34.88, 44.80], [34.96, 44.835], [35.02, 44.80],
    [35.09, 44.79], [35.19, 44.89], [35.24, 44.93], [35.27, 44.95],
    [35.36, 45.03], [35.40, 45.06], [35.60, 45.06], [35.85, 45.03],
    [36.10, 45.02], [36.27, 45.03], [36.45, 45.10], [36.56, 45.22],
    [36.50, 45.33], [36.44, 45.40], [36.15, 45.42], [35.95, 45.46],
    [35.85, 45.47], [35.72, 45.43], [35.45, 45.44], [35.28, 45.50],
    [35.18, 45.60], [35.08, 45.90], [35.03, 46.15], [35.03, 46.20],
    [33.62, 46.20],
  ],
  // Сиваш — залив между материком и Арабатской стрелкой (рисуется водой
  // поверх суши).
  sivash: [
    [33.72, 46.12], [34.20, 46.06], [34.60, 46.00], [34.98, 45.92],
    [35.00, 45.75], [34.70, 45.90], [34.30, 45.92], [33.90, 46.00],
  ],
  cities: [
    ["Севастополь", 33.53, 44.62], ["Симферополь", 34.10, 44.95],
    ["Ялта", 34.16, 44.50], ["Керчь", 36.45, 45.34],
    ["Феодосия", 35.38, 45.07], ["Судак", 34.97, 44.86],
    ["Алушта", 34.40, 44.68], ["Коктебель", 35.24, 44.97],
    ["Евпатория", 33.36, 45.21], ["Саки", 33.60, 45.14],
    ["Бахчисарай", 33.86, 44.76], ["Черноморское", 32.80, 45.49],
    ["Щёлкино", 35.82, 45.44],
  ],
};
MAP.H = Math.round(MAP.W * (MAP.LAT0 - MAP.LAT1) * 111 / ((MAP.LNG1 - MAP.LNG0) * 78.8));
MAP.SX = MAP.W / (MAP.LNG1 - MAP.LNG0);
MAP.SY = MAP.H / (MAP.LAT0 - MAP.LAT1);
MAP.px = lng => (lng - MAP.LNG0) * MAP.SX;
MAP.py = lat => (MAP.LAT0 - lat) * MAP.SY;

const TYPE_COLORS = {
  beach: "#f59e0b", castle: "#8b5cf6", palace: "#6366f1", winery: "#991b1b",
  nature: "#15803d", park: "#4d7c0f", city: "#0284c7", spa: "#0f766e",
  food: "#c2410c", museum: "#7e22ce", active: "#b45309", factory: "#db2777",
};

function renderMap() {
  const typeBtns = Object.keys(state.meta.tags).map(t => `
    <button class="chip-btn ${state.f.tag === t ? "active" : ""}" data-tag="${t}">${tagLabel(t)}</button>`).join("");
  const hasPlan = !!state.quizResult;
  view.innerHTML = `
    <div class="section">
      <div class="section-head">
        <h2>🗺 Карта Крыма</h2>
        <span class="sub">Схема полуострова — клик по точке открывает карточку места</span>
      </div>
      <div class="map-toolbar">
        <div class="filter-row" id="map-tags">${typeBtns}</div>
        <button class="btn btn-outline btn-sm" id="map-plan" ${hasPlan ? "" : "disabled"}
          title="${hasPlan ? "Показать маршрут плана по дням" : "Сначала пройдите квиз"}">
          🗓 Мой план
        </button>
      </div>
      <div class="map-wrap">
        <svg id="crimea-map" viewBox="0 0 ${MAP.W} ${MAP.H}" role="img"
          aria-label="Схема Крыма с точками"></svg>
      </div>
      <div class="map-legend" id="map-legend"></div>
    </div>`;
  $$("#map-tags .chip-btn").forEach(b => b.addEventListener("click", () => {
    state.f.tag = state.f.tag === b.dataset.tag ? "" : b.dataset.tag;
    renderMap();
  }));
  $("#map-plan").addEventListener("click", () => {
    state.mapShowPlan = !state.mapShowPlan;
    drawMap();
  });
  drawMap();
}

function drawMap() {
  const svg = $("#crimea-map");
  if (!svg) return;
  const pts = arr => arr.map(([lng, lat]) =>
    `${MAP.px(lng).toFixed(1)},${MAP.py(lat).toFixed(1)}`).join(" ");
  const items = state.attractions.filter(
    a => !state.f.tag || a.tags.includes(state.f.tag));

  const markers = items.map(a => {
    const meta = state.meta.types[a.type] || { emoji: "📍" };
    const color = TYPE_COLORS[a.type] || "#64748b";
    const fav = state.favs.has(a.id) ? ' class="fav-ring"' : "";
    return `<g class="marker" data-id="${a.id}" tabindex="0" role="button"
        aria-label="${esc(a.name)} — открыть карточку"
        transform="translate(${MAP.px(a.lng).toFixed(1)},${MAP.py(a.lat).toFixed(1)})">
      <title>${esc(a.name)} — ${esc(a.region)}</title>
      <circle${fav} r="14" fill="none" stroke="#e0475b" stroke-width="2" opacity="${state.favs.has(a.id) ? 1 : 0}"/>
      <circle r="11" fill="${color}" stroke="#fff" stroke-width="2"/>
      <text y="4.5" text-anchor="middle" font-size="11" pointer-events="none">${meta.emoji}</text>
    </g>`;
  }).join("");

  let planLayer = "";
  if (state.mapShowPlan && state.quizResult) {
    const stops = state.quizResult.itinerary.days.flatMap(d => d.stops);
    planLayer = `
      <polyline points="${stops.map(s =>
        `${MAP.px(s.lng).toFixed(1)},${MAP.py(s.lat).toFixed(1)}`).join(" ")}"
        fill="none" stroke="#f5a524" stroke-width="2.5" stroke-dasharray="7 5" opacity="0.9"/>
      ${stops.map((s, i) => `<g transform="translate(${MAP.px(s.lng).toFixed(1)},${MAP.py(s.lat).toFixed(1)})" pointer-events="none">
        <circle r="8" fill="#f5a524" stroke="#fff" stroke-width="2"/>
        <text y="3.5" text-anchor="middle" font-size="9" font-weight="700" fill="#3a2a05">${i + 1}</text>
      </g>`).join("")}`;
  }

  svg.innerHTML = `
    <defs>
      <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#c3e6ef"/>
        <stop offset="1" stop-color="#a8d8e8"/>
      </linearGradient>
    </defs>
    <rect x="0" y="0" width="${MAP.W}" height="${MAP.H}" fill="url(#sea)" rx="18"/>
    <polygon points="${pts(MAP.coast)}" fill="#f5eddb" stroke="#cbb98e" stroke-width="2.5" stroke-linejoin="round"/>
    <polygon points="${pts(MAP.sivash)}" fill="#b9dde9" stroke="#8fc3d4" stroke-width="1.5"/>
    <text class="sea-label" x="430" y="${MAP.H - 22}">Чёрное море</text>
    <text class="sea-label" x="790" y="118">Азовское море</text>
    <text class="sea-label small" x="462" y="98">Сиваш</text>
    <text class="sea-label small" x="925" y="252">Керченский пролив</text>
    <text class="sea-label small" x="352" y="20">материк</text>
    ${MAP.cities.map(([n, lng, lat]) =>
      `<text class="city-label" x="${MAP.px(lng).toFixed(1)}" y="${MAP.py(lat).toFixed(1)}">${n}</text>`).join("")}
    ${markers}
    <g id="plan-layer">${planLayer}</g>`;

  // легенда: только типы, представленные в текущей выборке
  const types = [...new Set(items.map(a => a.type))].sort();
  $("#map-legend").innerHTML = types.map(t => {
    const meta = state.meta.types[t] || { emoji: "📍", label: t };
    return `<span class="legend-item"><i style="background:${TYPE_COLORS[t] || "#64748b"}"></i>${meta.emoji} ${meta.label}</span>`;
  }).join("") + `<span class="legend-item"><i style="background:transparent;border:2px solid #e0475b;border-radius:50%"></i>❤ избранное</span>`;

  $$(".marker", svg).forEach(g => {
    g.addEventListener("click", () => openModal(g.dataset.id));
    g.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openModal(g.dataset.id); }
    });
  });
}

/* ---------------- router / init ---------------- */
const ROUTE_TITLES = {
  home: "Главная", catalog: "Каталог мест", map: "Карта Крыма",
  quiz: "Квиз и план поездки", news: "Новости Крыма",
};

function announce(text) {
  const el = $("#route-status");
  if (el) el.textContent = text;
}

function hashParts() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = h.split("?");
  return { path: path || "home", query: new URLSearchParams(query), rawQuery: query };
}

function route() {
  const { path, query, rawQuery } = hashParts();
  const navPath = path.startsWith("place/") ? "catalog" : path;
  // Уходим с каталога — снимаем наблюдатель догрузки: его «часовой»
  // сейчас исчезнет вместе с разметкой.
  if (navPath !== "catalog") { catObserver?.disconnect(); catObserver = null; }
  $$(".nav a").forEach(a => {
    const active = a.dataset.nav === navPath;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (path.startsWith("place/")) {
    // Прямая ссылка на место: каталог фоном + модалка поверх.
    // Если каталог уже отрисован — не перерисовываем (не сбрасываем скролл).
    if (state._lastRoute !== "catalog") renderCatalog();
    openModal(decodeURIComponent(path.slice(6)));
    state._lastRoute = "catalog";
    announce(`Карточка места открыта поверх каталога`);
    return;
  }
  if (path === "catalog") {
    // URL — источник правды: filters из ссылки побеждают локальные.
    if (rawQuery) state.f = CatalogLink.parseCatalogQuery(rawQuery);
    renderCatalog();
  }
  else if (path === "map") renderMap();
  else if (path === "quiz") {
    if (!state.quizResult && !state.planAutoDone) {
      const parsed = PlanLink.parsePlanParam(query.get("plan"));
      if (parsed) {
        state.planAutoDone = true;
        return autoEvaluatePlan(parsed);
      }
    }
    renderQuiz();
  }
  else if (path === "news") renderNews();
  else if (path === "favs") {
    // Временный маршрут: импорт избранного из ссылки и уход на главную.
    importFavsFromQuery(rawQuery);
    return;
  }
  else renderHome();
  state._lastRoute = navPath;
  announce(ROUTE_TITLES[navPath] || "Крым.Гид");
  window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", () => {
  $(".nav")?.classList.remove("open");
  $("#nav-toggle")?.setAttribute("aria-expanded", "false");
  route();
});
window.addEventListener("keydown", e => {
  if (e.key === "Escape" && $("#modal-root").innerHTML) {
    if (state._closeModal) state._closeModal();
    else $("#modal-root").innerHTML = "";
  }
});
window.addEventListener("afterprint", () => document.body.classList.remove("print-plan"));

$("#nav-toggle").addEventListener("click", () => {
  const nav = $(".nav");
  nav.classList.toggle("open");
  $("#nav-toggle").setAttribute("aria-expanded", String(nav.classList.contains("open")));
});

/* Skip-link: href="#view" не отдаём роутеру (hash не меняется),
   просто переносим фокус и скролл в <main>. */
$("#skip-link").addEventListener("click", e => {
  e.preventDefault();
  view.focus({ preventScroll: true });
  view.scrollIntoView();
});

(async function init() {
  loadFavs();
  // PWA: офлайн-оболочка (статика + последний ответ API)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  try {
    const [meta, areas, attr, quiz] = await Promise.all([
      api("/api/tags"), api("/api/areas"), api("/api/attractions"), api("/api/quiz"),
    ]);
    state.meta = meta;
    state.areas = areas.areas;
    state.attractions = attr.items;
    state.quiz = quiz;
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div>Не удалось загрузить данные приложения: ${e.message}</div>`;
    return;
  }
  try { await loadNews(); } catch (e) { /* badge останется в дефолте */ }
  api("/api/weather").then(d => { state.weather = d; route(); }).catch(() => {});
  api("/api/sea").then(d => { state.sea = d; route(); }).catch(() => {});
  api("/api/health").then(d => {
    const el = document.getElementById("app-version");
    if (el && d.version) el.textContent = "v" + d.version;
  }).catch(() => {});
  route();
  setInterval(() => { if (!document.hidden && state.news) loadNews().catch(() => {}); }, 10 * 60 * 1000);
})();
