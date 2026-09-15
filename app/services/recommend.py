"""Матч-мейкер: квиз → рекомендации.

Каждое место в каталоге — набор тегов, сезонность, бюджет, длительность
и способ добраться. Ответы квиза конвертируем в баллы и сортируем.
"""
from .load import get_attractions

TAGS = {
    "beach": "пляжи", "nature": "природа", "history": "история",
    "culture": "дворцы и музеи", "food": "гастрономия", "wine": "вино",
    "active": "активный отдых", "family": "с детьми", "photo": "фотогении",
    "spa": "спа и грязели", "city": "набережные и города", "view": "панорамы",
    "free": "бесплатно", "romance": "для двоих",
}

TAG_EMOJI = {
    "beach": "🏖️", "nature": "🌿", "history": "🏛️", "culture": "🖼️",
    "food": "🍽️", "wine": "🍷", "active": "🥾", "family": "👨‍‍👧",
    "photo": "📸", "spa": "🧖", "city": "🏙️", "view": "🌄",
    "free": "🆓", "romance": "💞",
}

TYPE_META = {
    "beach": {"emoji": "🏖️", "label": "Пляж", "img": "cat_beach.jpg"},
    "castle": {"emoji": "🏰", "label": "Крепость", "img": "cat_history.jpg"},
    "palace": {"emoji": "🏛️", "label": "Дворец", "img": "cat_history.jpg"},
    "winery": {"emoji": "🍷", "label": "Вина", "img": "cat_wine.jpg"},
    "nature": {"emoji": "🌿", "label": "Природа", "img": "cat_nature.jpg"},
    "park": {"emoji": "🌳", "label": "Парк", "img": "cat_nature.jpg"},
    "city": {"emoji": "🏙️", "label": "Город", "img": "cat_city.jpg"},
    "spa": {"emoji": "🧖", "label": "Спа", "img": "cat_nature.jpg"},
    "food": {"emoji": "🍽️", "label": "Гастро", "img": "cat_food.jpg"},
    "museum": {"emoji": "🖼️", "label": "Музей", "img": "cat_history.jpg"},
    "active": {"emoji": "🥾", "label": "Активный", "img": "cat_active.jpg"},
    "factory": {"emoji": "🎡", "label": "Детям", "img": "cat_family.jpg"},
}

PROFILES = {
    "beach": {
        "title": "Море, солнце и спокойствие",
        "emoji": "🌅",
        "summary": "Ваш профиль — классический пляжный отдых: купание, "
                   "набережные и неспешные прогулки у воды.",
    },
    "nature": {
        "title": "Дерзкий путеводитель",
        "emoji": "🥾",
        "summary": "Вы выбираете Крым с его диких сторон: ущелья, плато, "
                   "пещеры и смотровые, куда не доедет толпа.",
    },
    "history": {
        "title": "Исследователь прошлого",
        "emoji": "🏛️",
        "summary": "Ваш маршрут пропитан историей: от греческих полисов "
                   "до дворцов Романовых.",
    },
    "food": {
        "title": "Гастро-поездка",
        "emoji": "🍷",
        "summary": "Крым для вас — это вкус: вина ЮБК, рынки, сыроварни "
                   "и фермерские продукты.",
    },
    "wine": {
        "title": "Винная карта Крыма",
        "emoji": "🍷",
        "summary": "Ваш маршрут — по подвалам и винодельням: мускаты ЮБК, "
                   "винодельни Керчи и дегустации с видом на море.",
    },
    "family": {
        "title": "Крым всей семьёй",
        "emoji": "👨‍‍👧",
        "summary": "Маршрут подобран так, чтобы всем было интересно: "
                   "детям — приключения, взрослым — спокойствие.",
    },
    "photo": {
        "title": "Художник-путешественник",
        "emoji": "📸",
        "summary": "Ваш приоритет — кадры: закатные точки, утёсы, "
                   "цветы и архитектурные декорации.",
    },
}

DAYS_BY_DURATION = {"1-2": 5, "3-5": 8, "6-10": 12, "10+": 16}
ITINERARY_DAYS = {"1-2": 2, "3-5": 4, "6-10": 7, "10+": 12}

AREA_LABEL = {
    "Южный берег": "Южный берег",
    "Центральный": "Центральный Крым",
    "Восточный": "Восточный Крым",
    "Западный": "Западный Крым",
}

SEASON_LABEL = {
    "summer": "летом", "spring": "весной", "autumn": "осенью",
    "winter": "зимой", "any": "в любое время года",
}


def plan_itinerary(recs: list[dict], duration_key: str) -> dict:
    """Разложить рекомендации по дням: кластеризация по районам,
    3 остановки максимум в день, «большие» места — на целый день."""
    n_days = ITINERARY_DAYS.get(duration_key, 4)
    by_area: dict[str, list[dict]] = {}
    for r in recs:
        by_area.setdefault(r.get("area", "Крым"), []).append(r)
    for v in by_area.values():
        v.sort(key=lambda x: -x.get("duration_h", 3))

    days = []
    for d in range(1, n_days + 1):
        if not any(by_area.values()):
            break
        area = max(by_area, key=lambda a: len(by_area[a]))
        pool = by_area[area]
        stops: list[dict] = []
        total_h = 0.0
        while pool and len(stops) < 3 and total_h < 7:
            it = pool[0]
            h = it.get("duration_h", 3)
            if h >= 6:  # «большая» точка — занимает весь день
                it["slot"] = "full"
                stops.append(it)
                pool.pop(0)
                break
            it["slot"] = "morning" if not stops else "afternoon"
            stops.append(it)
            pool.pop(0)
            total_h += h
        if not stops:
            break
        if len(stops) > 1:
            stops[0]["slot"] = "morning"
            if stops[-1].get("duration_h", 3) <= 2.5:
                stops[-1]["slot"] = "evening"
            elif len(stops) == 2:
                stops[-1]["slot"] = "afternoon"

        tag_counts: dict[str, int] = {}
        for s in stops:
            for t in s.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        top_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])][:2]
        days.append({
            "day": d,
            "area": area,
            "area_label": AREA_LABEL.get(area, area),
            "tags": top_tags,
            "stops": stops,
        })

    reserve = [it for v in by_area.values() for it in v]
    return {"days": days, "reserve": reserve, "n_days": n_days}


def _score_attraction(a: dict, ans: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    # 1) Совпадение с интересами — главный вклад.
    matched = [t for t in ans.get("purpose", []) if t in a["tags"]]
    if matched:
        score += 3.0 * len(matched)
        reasons.append("Совпадает: " + ", ".join(TAGS.get(t, t) for t in matched[:3]))

    # 2) Сезон.
    season = ans.get("season", "any")
    if season != "any":
        if season in a.get("season", []):
            score += 1.5
            reasons.append(f"Отличное место {SEASON_LABEL[season]}")
        else:
            score -= 1.0

    # 3) Бюджет.
    budget = {"economy": 1, "comfort": 2, "premium": 3}.get(ans.get("budget", "comfort"), 2)
    if a.get("budget", 2) <= budget:
        score += 1.0
    else:
        score -= 2.0
        reasons.append("Дороже, чем ваш бюджет")

    # 4) Состав компании.
    party = ans.get("party", "solo")
    if party == "family" and "family" in a["tags"]:
        score += 1.5
        reasons.append("Отличный вариант с детьми")
    if party == "couple" and ("romance" in a["tags"] or "photo" in a["tags"] or "view" in a["tags"]):
        score += 1.0
    if party == "friends" and ("active" in a["tags"] or "food" in a["tags"]):
        score += 1.0

    # 5) Темп.
    tempo = ans.get("tempo", "medium")
    hours = a.get("duration_h", 3)
    if tempo == "active" and hours <= 4:
        score += 0.5
    if tempo == "relax" and hours >= 3 and (
        "beach" in a["tags"] or "spa" in a["tags"] or "nature" in a["tags"]
    ):
        score += 0.5
        reasons.append("Тихий и неспешный отдых")

    # 6) Транспорт: без машины часть мест недоступна.
    if ans.get("transport", "car") == "transit" and a.get("access") == "car":
        score -= 3.0

    # 7) Популярность — небольшой бонус.
    score += (a.get("rating", 4.0) - 4.0)

    return score, reasons


def evaluate(answers: dict, news_items: list[dict] | None = None) -> dict:
    """Ответы квиза → профиль, список рекомендаций, новости по интересам."""
    answers = {
        "purpose": [t for t in answers.get("purpose", []) if t in TAGS][:3] or ["beach"],
        "season": answers.get("season", "any"),
        "tempo": answers.get("tempo", "medium"),
        "budget": answers.get("budget", "comfort"),
        "party": answers.get("party", "solo"),
        "duration": answers.get("duration", "3-5"),
        "transport": answers.get("transport", "car"),
    }

    scored = []
    for a in get_attractions():
        score, reasons = _score_attraction(a, answers)
        if score >= 2.5:
            meta = TYPE_META.get(a["type"], {"emoji": "📍", "label": a["type"], "img": "cat_nature.jpg"})
            scored.append((score, {**a, "type_meta": meta, "score": round(score, 1),
                                    "reasons": reasons}))
    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[:DAYS_BY_DURATION.get(answers["duration"], 8)]

    # Профиль по основному интересу.
    profile = PROFILES.get(answers["purpose"][0], PROFILES["beach"])

    # Новости по интересам: берём крымские новости, чьи темы пересекаются
    # с интересами, или с высокой релевантностью.
    purpose_topics = {"beach": {"beach", "weather"}, "nature": {"nature", "events"},
                      "history": {"history", "events"}, "food": {"food", "events"},
                      "wine": {"food", "events"}, "active": {"events", "transport"},
                      "family": {"events", "beach"}, "photo": {"events", "weather"},
                      "spa": {"safety", "beach"}, "city": {"transport", "events"}}
    want = set()
    for t in answers["purpose"]:
        want |= purpose_topics.get(t, set())
    news = []
    for it in news_items or []:
        if it.get("crimea_score", 0) <= 0:
            continue
        if set(it.get("topics", [])) & want or it.get("crimea_score", 0) >= 5:
            news.append(it)
        if len(news) >= 4:
            break

    transport_hint = (
        "🚗 На машине можно заехать в самые удалённые точки — "
        "смело включайте в маршрут пещеры, мысы и узкие горные дороги."
        if answers["transport"] == "car"
        else "🚌 Без машины ориентируйтесь на курортные города с разветвлённой "
             "сетью маршруток и электричек: Ялта, Евпатория, Судак, Керчь, Феодосия."
    )

    return {
        "profile": profile,
        "answers": answers,
        "count": len(top),
        "days_hint": answers["duration"],
        "recommendations": [x[1] for x in top],
        "itinerary": plan_itinerary([x[1] for x in top], answers["duration"]),
        "news": news,
        "transport_hint": transport_hint,
        "all_matched": len(scored),
    }
