"""Матч-мейкер: квиз → рекомендации.

Каждое место в каталоге — набор тегов, сезонность, бюджет, длительность
и способ добраться. Ответы квиза конвертируем в баллы и сортируем.
"""

from .load import get_attractions

TAGS = {
    "beach": "пляжи",
    "nature": "природа",
    "history": "история",
    "culture": "дворцы и музеи",
    "food": "гастрономия",
    "wine": "вино",
    "active": "активный отдых",
    "extreme": "экстрим и дайвинг",
    "family": "с детьми",
    "photo": "фотогении",
    "spa": "спа и грязели",
    "city": "набережные и города",
    "view": "панорамы",
    "free": "бесплатно",
    "romance": "для двоих",
}

# Бюджет: два числа у места вместо одной догадки. `price` — минимум, за
# который место доступно (0 — вход свободный), `budget` — полоса самой
# дорогой цены из `price_hint` (см. docs/data.md). Пороги те же, что в
# подсказках квиза («до 1 000 ₽», «1 000–3 000 ₽»); тест сверяет числа
# с текстом `quiz.json`, чтобы вопрос и матч-мейкер не разъехались.
BUDGET_CEILING = {"economy": 1000, "comfort": 3000}
BUDGET_PREMIUM_LEVEL = 3  # у премиума потолка нет — только вкус к дорогому
REASON_TOO_PRICEY = "Дороже, чем ваш бюджет"
REASON_PREMIUM = "Премиум-впечатление"
REASON_CHILDREN = "Отличный вариант с детьми"
REASON_RELAX = "Тихий и неспешный отдых"
# Готовые фразы причин: их требует словарь локали (`test_reasons_are_translatable`).
REASON_PHRASES = (REASON_TOO_PRICEY, REASON_PREMIUM, REASON_CHILDREN, REASON_RELAX)

TAG_EMOJI = {
    "beach": "🏖️",
    "nature": "🌿",
    "history": "🏛️",
    "culture": "🖼️",
    "food": "🍽️",
    "wine": "🍷",
    "active": "🥾",
    "extreme": "🤿",
    "family": "👨‍‍👧",
    "photo": "📸",
    "spa": "🧖",
    "city": "🏙️",
    "view": "🌄",
    "free": "🆓",
    "romance": "💞",
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
    "culture": {
        "title": "Культурный маршрут",
        "emoji": "🖼️",
        "summary": "В поездке вам важны музеи, дворцовые ансамбли, "
        "выставки и истории, которые раскрывают характер полуострова.",
    },
    "food": {
        "title": "Гастро-поездка",
        "emoji": "🍽️",
        "summary": "Крым для вас — это вкус: рынки, сыроварни, "
        "фермерские продукты и локальные специалитеты.",
    },
    "wine": {
        "title": "Винная карта Крыма",
        "emoji": "🍷",
        "summary": "Ваш маршрут — по подвалам и винодельням: мускаты ЮБК, "
        "винодельни Керчи и дегустации с видом на море.",
    },
    "active": {
        "title": "Активный Крым",
        "emoji": "🥾",
        "summary": "Лучшие дни для вас — это тропы, подъёмы, пещерные города "
        "и маршруты, где усталость превращается в впечатления.",
    },
    "extreme": {
        "title": "Крым на адреналине",
        "emoji": "🤿",
        "summary": "Вам нужны ветер и глубина: дайвинг на Тарханкуте, кайт "
        "на Азовском, полёты над Коктебелем и грунтовки к диким бухтам.",
    },
    "family": {
        "title": "Крым всей семьёй",
        "emoji": "👨‍👩‍👧",
        "summary": "Маршрут подобран так, чтобы всем было интересно: "
        "детям — приключения, взрослым — спокойствие.",
    },
    "photo": {
        "title": "Художник-путешественник",
        "emoji": "📸",
        "summary": "Ваш приоритет — кадры: закатные точки, утёсы, "
        "цветы и архитектурные декорации.",
    },
    "spa": {
        "title": "Перезагрузка у воды",
        "emoji": "🧖",
        "summary": "В фокусе — мягкий темп, грязевые озёра, спа-точки "
        "и места, где удобно восстановиться без гонки по маршруту.",
    },
    "city": {
        "title": "Городские прогулки",
        "emoji": "🏙️",
        "summary": "Вам ближе набережные, старые кварталы, музеи рядом "
        "с кафе и понятная логистика без дальних переездов.",
    },
    "view": {
        "title": "Охотник за панорамами",
        "emoji": "🌄",
        "summary": "Маршрут строится вокруг смотровых, горных серпантинов, "
        "мысов и видов, ради которых хочется задержаться подольше.",
    },
    "free": {
        "title": "Крым без лишних трат",
        "emoji": "🆓",
        "summary": "Выбираем бесплатные и недорогие места: прогулки, пляжи, "
        "видовые точки и природные маршруты с сильными впечатлениями.",
    },
    "romance": {
        "title": "Путешествие для двоих",
        "emoji": "💞",
        "summary": "Ваш Крым — это закаты, тихие бухты, дворцовые парки "
        "и маршруты, где легко оставить место для спонтанности.",
    },
}

PURPOSE_TOPICS = {
    "beach": {"beach", "weather"},
    "nature": {"nature", "weather", "events"},
    "history": {"history", "events"},
    "culture": {"history", "events"},
    "food": {"food", "events"},
    "wine": {"food", "events"},
    "active": {"nature", "events", "transport"},
    "extreme": {"weather", "safety", "nature"},
    "family": {"events", "beach", "safety"},
    "photo": {"nature", "weather", "events"},
    "spa": {"safety", "beach", "weather"},
    "city": {"transport", "events", "history"},
    "view": {"nature", "weather"},
    "free": {"events", "transport", "beach"},
    "romance": {"beach", "weather", "events"},
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
    "summer": "летом",
    "spring": "весной",
    "autumn": "осенью",
    "winter": "зимой",
    "any": "в любое время года",
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
        days.append(
            {
                "day": d,
                "area": area,
                "area_label": AREA_LABEL.get(area, area),
                "tags": top_tags,
                "stops": stops,
            }
        )

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

    # 3) Бюджет — по цене, а не по догадке. `price` — минимум, за который
    #    место доступно: эконом платит за вход, поэтому место дороже его
    #    потолка получает минус и причину. Премиум вход не ограничивает
    #    и предпочитает места с дорогими впечатлениями (`budget` = 3) —
    #    иначе ответ «премиум» ничего не менял: раньше таких мест было одно.
    answer_budget = ans.get("budget", "comfort")
    ceiling = BUDGET_CEILING.get(answer_budget)
    if ceiling is not None and a.get("price", 0) > ceiling:
        score -= 2.0
        reasons.append(REASON_TOO_PRICEY)
    else:
        score += 1.0
    if answer_budget == "premium" and a.get("budget", 1) >= BUDGET_PREMIUM_LEVEL:
        score += 1.0
        reasons.append(REASON_PREMIUM)

    # 4) Состав компании.
    party = ans.get("party", "solo")
    if party == "family" and "family" in a["tags"]:
        score += 1.5
        reasons.append(REASON_CHILDREN)
    couple_tags = {"romance", "photo", "view"}
    if party == "couple" and couple_tags & set(a["tags"]):
        score += 1.0
    if party == "friends" and (
        "active" in a["tags"] or "food" in a["tags"] or "extreme" in a["tags"]
    ):
        score += 1.0

    # 5) Темп.
    tempo = ans.get("tempo", "medium")
    hours = a.get("duration_h", 3)
    if tempo == "active" and hours <= 4:
        score += 0.5
    if (
        tempo == "relax"
        and hours >= 3
        and ("beach" in a["tags"] or "spa" in a["tags"] or "nature" in a["tags"])
    ):
        score += 0.5
        reasons.append(REASON_RELAX)

    # 6) Транспорт: без машины часть мест недоступна.
    if ans.get("transport", "car") == "transit" and a.get("access") == "car":
        score -= 3.0

    # 7) Популярность — небольшой бонус.
    score += a.get("rating", 4.0) - 4.0

    return score, reasons


def evaluate(answers: dict, news_items: list[dict] | None = None) -> dict:
    """Ответы квиза → профиль, список рекомендаций, новости по интересам."""
    answers = {
        "purpose": [t for t in answers.get("purpose", []) if t in TAGS][:3]
        or ["beach"],
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
            fallback = {"emoji": "📍", "label": a["type"], "img": "cat_nature.jpg"}
            meta = TYPE_META.get(a["type"], fallback)
            scored.append(
                (
                    score,
                    {
                        **a,
                        "type_meta": meta,
                        "score": round(score, 1),
                        "reasons": reasons,
                    },
                )
            )
    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[: DAYS_BY_DURATION.get(answers["duration"], 8)]

    # Профиль по основному интересу.
    profile = PROFILES.get(answers["purpose"][0], PROFILES["beach"])

    # Новости по интересам: берём крымские новости, чьи темы пересекаются
    # с интересами, или с высокой релевантностью.
    want = set()
    for t in answers["purpose"]:
        want |= PURPOSE_TOPICS.get(t, set())
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
