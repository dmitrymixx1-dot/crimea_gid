/* ============ Крым.Гид — SPA ============ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const view = $("#view");

const TOPIC_LABELS = {
  beach: "🏖️ Пляжи", weather: "🌤️ Погода", transport: "🚗 Транспорт",
  events: "🎉 События", food: "🍷 Гастро", safety: " Безопасность",
  history: "🏛️ История",
};

const state = {
  meta: { tags: {}, types: {} },
  attractions: [],
  areas: [],
  quiz: null,
  news: null,
  f: { q: "", area: "", tag: "" },
  q: { step: 0, answers: {} },
  quizResult: null,
  newsView: { topic: "all", onlyCrimea: true },
  newsLoading: false,
};

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

function hashParts() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = h.split("?");
  return { path: path || "home", query: new URLSearchParams(query) };
}

function tagLabel(t) { return state.meta.tags[t] || t; }

function budgetIcons(b) { return "₽".repeat(b) + `<span class="muted">${"₽".repeat(3 - b)}</span>`; }

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
  const meta = state.meta.types[a.type] || { emoji: "📍", img: "cat_nature.jpg" };
  const chips = a.tags.slice(0, 3)
    .map(t => `<span class="chip">${tagLabel(t)}</span>`).join("");
  return `
    <article class="card" data-id="${a.id}">
      <div class="card-img">
        <img src="/static/img/${meta.img}" alt="" loading="lazy"
             onerror="this.remove()" />
        <div class="emoji">${meta.emoji}</div>
      </div>
      <div class="card-body">
        <h3 class="card-title">${a.name}</h3>
        <div class="card-region">📍 ${a.region}</div>
        <p class="card-desc">${a.description}</p>
        <div class="card-chips">${chips}</div>
        <div class="card-meta">
          <span><span class="star">★</span> <b>${a.rating.toFixed(1)}</b></span>
          <span>${budgetIcons(a.budget)}</span>
          <span>⏱ ${a.duration_h} ч</span>
        </div>
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
        <span class="source-badge">${it.source}</span>
        <span class="news-time">${fmtTime(it.published)}</span>
      </div>
      <div class="news-body">
        <h3 class="news-title"><a href="${it.link}" target="_blank" rel="noopener">${it.title}</a></h3>
        ${it.summary ? `<p class="news-summary">${it.summary}</p>` : ""}
        ${topics ? `<div class="news-topics">${topics}</div>` : ""}
      </div>
    </div>`;
}

/* ---------------- home ---------------- */
function renderHome() {
  const top = [...state.attractions].sort((a, b) => b.rating - a.rating).slice(0, 4);
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
      <img src="/static/img/hero.jpg" alt="Южный берег Крыма" onerror="this.style.display='none'" />
      <div class="hero-content">
        <h1>Крым подскажет,<br />куда вам сходить</h1>
        <p>Пройдите квиз за минуту — соберём маршрут под ваши интересы.
           А ещё — каталог проверенных мест и живая лента новостей полуострова.</p>
        <div class="hero-actions">
          <a class="btn btn-sun" href="#/quiz">🎯 Пройти квиз</a>
          <a class="btn btn-ghost" href="#/catalog">Смотреть каталог</a>
        </div>
        <div class="hero-stats">
          <span class="hero-stat">📍 ${state.attractions.length} мест</span>
          <span class="hero-stat">❓ ${state.quiz ? state.quiz.questions.length : 7} вопросов</span>
          <span class="hero-stat">📰 ${n ? n.sources.length : 5} источников новостей</span>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Ваш профиль отдыха</h2>
        <span class="sub">Выберите настроение — откроется каталог по теме</span>
      </div>
      <div class="grid">
        ${cats.map(([t, img]) => `
          <a class="card cat-tile" href="#/catalog?tag=${t}" style="text-decoration:none">
            <div class="card-img"><img src="/static/img/${img}" alt="" loading="lazy" onerror="this.remove()"/></div>
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
  `;
  bindCards();
}

/* ---------------- catalog ---------------- */
function renderCatalog() {
  const { path, query } = hashParts();
  const presetTag = query.get("tag") || "";
  if (presetTag) state.f.tag = presetTag;
  const tagBtns = Object.keys(state.meta.tags).map(t => `
    <button class="chip-btn ${state.f.tag === t ? "active" : ""}" data-tag="${t}">${tagLabel(t)}</button>`).join("");
  view.innerHTML = `
    <div class="section">
      <div class="section-head"><h2>Каталог мест</h2><span class="count-note" id="cat-count"></span></div>
      <div class="filters">
        <div class="filter-row">
          <input class="search" id="cat-search" placeholder="Поиск: Ласточкино, вино, пляж…" value="${state.f.q}" />
          <select class="select" id="cat-area">
            <option value="">Вся география</option>
            ${state.areas.map(a => `<option ${state.f.area === a ? "selected" : ""}>${a}</option>`).join("")}
          </select>
        </div>
        <div class="filter-row" id="cat-tags">${tagBtns}</div>
      </div>
      <div class="grid" id="cat-grid"></div>
    </div>`;
  $("#cat-search").addEventListener("input", e => { state.f.q = e.target.value; renderCatGrid(); });
  $("#cat-area").addEventListener("change", e => { state.f.area = e.target.value; renderCatGrid(); });
  $$("#cat-tags .chip-btn").forEach(b => b.addEventListener("click", () => {
    state.f.tag = state.f.tag === b.dataset.tag ? "" : b.dataset.tag;
    renderCatalog();
  }));
  renderCatGrid();
}

function renderCatGrid() {
  const grid = $("#cat-grid");
  if (!grid) return;
  const q = state.f.q.toLowerCase();
  const items = state.attractions.filter(a =>
    (!state.f.area || a.area === state.f.area) &&
    (!state.f.tag || a.tags.includes(state.f.tag)) &&
    (!q || a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q)));
  grid.innerHTML = items.length
    ? items.map(attractionCard).join("")
    : `<div class="empty" style="grid-column:1/-1"><div class="big">🔍</div>Ничего не нашлось. Попробуйте убрать фильтры.</div>`;
  $("#cat-count").textContent = `Найдено: ${items.length}`;
  bindCards(grid);
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
          <img class="rec-img" src="/static/img/${a.type_meta.img}" alt="" onerror="this.style.background='var(--sea-soft)'" />
          <div class="rec-body">
            <h3>${a.type_meta.emoji} ${a.name}</h3>
            <div class="rec-region">📍 ${a.region} · ⏱ ${a.duration_h} ч · <span class="star">★</span> ${a.rating.toFixed(1)}</div>
            <div class="rec-reasons">
              ${a.reasons.map(x => `<span class="chip">${x}</span>`).join("")}
            </div>
          </div>
          <span class="rec-score">${a.score}</span>
        </div>`).join("")}
      ${r.news && r.news.length ? `
        <div class="section-head" style="margin-top:26px">
          <h2 style="font-size:20px">Новости по вашим интересам</h2>
        </div>
        ${r.news.map(newsItemHTML).join("")}` : ""}
      <div style="display:flex;gap:10px;margin-top:26px;flex-wrap:wrap">
        <button class="btn btn-primary" id="q-again">🔄 Пройти заново</button>
        <a class="btn btn-outline" href="#/catalog">Открыть каталог</a>
      </div>
    </div>`;
  $$(".rec-row").forEach(el => el.addEventListener("click", () => openModal(el.dataset.id)));
  $("#q-again").addEventListener("click", () => {
    state.q = { step: 0, answers: {} };
    state.quizResult = null;
    renderQuiz();
  });
}

/* ---------------- news ---------------- */
async function renderNews(refresh = false) {
  if (refresh) state.newsLoading = true;
  view.innerHTML = `
    <div class="section">
      <div class="news-head">
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
  const items = pool.filter(x => state.newsView.topic === "all"
    || (x.topics || []).includes(state.newsView.topic));
  $("#news-list").innerHTML = items.length
    ? items.map(newsItemHTML).join("")
    : `<div class="empty"><div class="big">📭</div>По этой теме пока пусто.</div>`;
}

/* ---------------- modal ---------------- */
function bindCards(root = view) {
  $$(".card[data-id], .rec-row[data-id]", root).forEach(el =>
    el.addEventListener("click", () => openModal(el.dataset.id)));
}

function openModal(id) {
  const a = state.attractions.find(x => x.id === id);
  if (!a) return;
  const meta = state.meta.types[a.type] || { emoji: "📍", img: "cat_nature.jpg" };
  const mapUrl = "https://yandex.ru/maps/?text=" + encodeURIComponent(`Крым, ${a.name}`);
  $("#modal-root").innerHTML = `
    <div class="overlay" id="overlay">
      <div class="modal">
        <div class="modal-img">
          <img src="/static/img/${meta.img}" alt="" onerror="this.style.display='none'" />
          <button class="modal-close" id="m-close" aria-label="Закрыть">✕</button>
        </div>
        <div class="modal-body">
          <h2>${meta.emoji} ${a.name}</h2>
          <div class="muted">📍 ${a.region} · ${a.area}</div>
          <p style="margin-top:12px">${a.description}</p>
          <div class="facts">
            <div class="fact"><span class="k">Сезон</span>${a.season.map(s => ({ summer: "☀️ лето", spring: "🌸 весна", autumn: "🍂 осень", winter: "❄️ зима" }[s] || s)).join(", ")}</div>
            <div class="fact"><span class="k">Бюджет</span>${budgetIcons(a.budget)} · ${a.price_hint}</div>
            <div class="fact"><span class="k">Длительность</span>≈ ${a.duration_h} ч</div>
            <div class="fact"><span class="k">Рейтинг</span><span class="star">★</span> ${a.rating.toFixed(1)} / 5</div>
          </div>
          <div class="card-chips">${a.tags.map(t => `<span class="chip">${tagLabel(t)}</span>`).join("")}</div>
          <div class="tip">💡 ${a.tips}</div>
          <div class="modal-actions">
            <a class="btn btn-primary btn-sm" href="${mapUrl}" target="_blank" rel="noopener">🗺 Открыть на карте</a>
            <button class="btn btn-outline btn-sm" id="m-close2">Закрыть</button>
          </div>
        </div>
      </div>
    </div>`;
  const close = () => { $("#modal-root").innerHTML = ""; document.body.style.overflow = ""; };
  $("#m-close").addEventListener("click", close);
  $("#m-close2").addEventListener("click", close);
  $("#overlay").addEventListener("click", e => { if (e.target.id === "overlay") close(); });
  document.body.style.overflow = "hidden";
}

/* ---------------- router / init ---------------- */
function route() {
  const { path } = hashParts();
  $$(".nav a").forEach(a => a.classList.toggle("active", a.dataset.nav === path || (path === "home" && a.dataset.nav === "home")));
  if (path === "catalog") renderCatalog();
  else if (path === "quiz") renderQuiz();
  else if (path === "news") renderNews();
  else renderHome();
  window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", route);
window.addEventListener("keydown", e => { if (e.key === "Escape") $("#modal-root").innerHTML = ""; });

(async function init() {
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
  route();
  setInterval(() => { if (!document.hidden && state.news) loadNews().catch(() => {}); }, 10 * 60 * 1000);
})();
