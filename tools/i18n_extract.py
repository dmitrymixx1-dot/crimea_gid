#!/usr/bin/env python3
"""Сбор русских строк интерфейса из фронтенда (dev-инструмент).

Зачем: английская локаль держится на словаре `static/i18n/en.json`,
где ключ — русская строка ровно в том виде, в каком она попадает в DOM.
Словарь обязан покрывать интерфейс, иначе «английский» экран остаётся
наполовину русским, а молчаливые дыры в локали никто не замечает.

Скрипт делает то, что делает браузер: разбирает `static/index.html` и
`static/app.js`, вынимает текстовые куски между тегами и значения
переводимых атрибутов — и сверяет их со словарём.
`tests/test_i18n.py` вызывает его как библиотеку, поэтому покрытие
локали не может устареть незаметно: поменяли строку в разметке — тест
покажет пропавший ключ.

Что считается «строкой интерфейса»:
  * текст между тегами (`<h2>Каталог мест</h2>` → «Каталог мест»);
  * значения `title` / `aria-label` / `placeholder` / `alt`;
  * содержимое `t("…")` — там ключ и есть первый аргумент.
Комментарии, классы, `data-*`, CSS и JS-логика в словарь не просятся.

Вставка `${…}` посреди фразы — сигнал, что строку надо не докладывать в
словарь, а выносить шаблоном: `t("Показано {seen} из {total}", …)`. DOM
показывает такую фразу одним текстовым узлом, и ключ-ог piece («Показано»,
«из») с ним никогда не совпадёт. Такие куски скрипт печатает отдельно.

Использование:
    python tools/i18n_extract.py                 # сводка и список дыр
    python tools/i18n_extract.py --missing       # только отсутствующие ключи
    python tools/i18n_extract.py --keys          # все ключи (скелет словаря)
    python tools/i18n_extract.py --json          # машинный вывод (для теста)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
# Что сканируем. Модули вида `rate-limit.js` — не здесь: их подписи живут
# рядом с логикой, EN-вариант отдаёт сам модуль, и ключом словаря такой
# текст быть не должен (проверяется собственными JS-тестами).
FRONT_SOURCES = [STATIC / "index.html", STATIC / "app.js"]
BUNDLE = STATIC / "i18n" / "en.json"
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
# Что переводить не принято: бренд и подпись языка на кнопке. Ключ обязан
# остаться в исходнике (иначе перевод «мёртвый»), но словаря он не требует.
EXEMPT = {
    "Крым.": "бренд: не переводим",
    "Гид": "бренд: не переводим",
    "Крым.Гид": "бренд: не переводим",
    "Рус": "название языка на кнопке переключения",
    "Крым,": "префикс запроса в Яндекс.Карты: по-русски ищется точнее",
}
NUMBER_RE = re.compile(r"\d+(?:[.,:–— -]\d+)*")
# Атрибуты, которые переводит обходчик DOM (см. I18n.TRANSLATE_ATTRS).
TRANSLATE_ATTRS = ("title", "aria-label", "placeholder", "alt")
ATTR_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in TRANSLATE_ATTRS) + r")\s*=\s*\"([^\"]*)\""
)
TAG_RE = re.compile(r"<[^<>]*>")
SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.I)
STYLE_RE = re.compile(r"<style[\s\S]*?</style>", re.I)
COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
# Разделитель текстовых узлов: на его месте в DOM — вставка значения.
SEP = "\x00"
# Так `I18n.fold()` помечает числовую группу в ключе словаря.
FOLD = "{n}"
# После чего `/` начинает регулярку, а не деление (эвристика как в линтерах).
AFTER_REGEX = set("(,=:[!&|?{};\n+-*%<>~^")
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}


def normalize(text: str) -> str:
    """Как `I18n.normalize`: пробельные отступы схлопнуты, края срезаны."""
    return re.sub(r"\s+", " ", text).strip()


def fold_key(text: str) -> str:
    """Как `I18n.fold`: числа становятся `{n}` — альтернативная форма ключа.

    Словарь может знать либо буквал («3–5 дней»), либо свёрнутую подпись
    («через {n} минут»): для строк, которые собираются из кусков, буквал
    не годится — в нём живёт конкретное число. Тест принимает обе формы.
    """
    return NUMBER_RE.sub(FOLD, normalize(text))


def has_cyrillic(text: str) -> bool:
    return bool(CYRILLIC.search(text))


# ---------------------------------------------------------------- скан JS
#
# Один проход: комментарии выбрасываем, строковые литералы собираем,
# шаблонные строки режем на куски по `${…}` (в DOM это граница узла), а
# литералы внутри вставок собираем отдельно — они те же самые тексты.


def scan_js(src: str) -> list[str]:
    out: list[str] = []
    _scan_code(src, 0, out)
    return out


def _scan_code(src: str, i: int, out: list[str]) -> int:
    """Читает код до конца `src`; возвращает позицию остановки."""
    n = len(src)
    prev = "\n"  # последний значимый символ вне строк — для эвристики regex
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _read_string(src, i, c, False, out)
            prev = c
            continue
        if c == "`":
            i = _read_string(src, i, "`", True, out)
            prev = c
            continue
        if c == "/" and src[i + 1 : i + 2] == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and src[i + 1 : i + 2] == "*":
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            prev = " "
            continue
        if c == "/" and prev in AFTER_REGEX:
            i = _skip_regex(src, i)
            prev = "/"
            continue
        if not c.isspace():
            prev = c
        i += 1
    return i


def _read_string(src: str, start: int, quote: str, raw: bool, out: list[str]) -> int:
    """Позиция за закрывающей кавычкой; содержимое строки — в `out`."""
    i, n = start + 1, len(src)
    buf: list[str] = []
    while i < n:
        c = src[i]
        if c == "\\":
            nxt = src[i + 1 : i + 2]
            buf.append("\n" if (nxt == "n" and raw) else ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == quote:
            out.append("".join(buf))
            return i + 1
        if raw and c == "$" and src[i + 1 : i + 2] == "{":
            stop = _expression_end(src, _expression_start=i + 1)
            _scan_code(src[i + 2 : stop], 0, out)
            buf.append(SEP)
            i = stop + 1
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf))
    return n


def _skip_regex(src: str, start: int) -> int:
    """Пройти литерал регулярки, чтобы её кавычки не открыли строку."""
    i, n = start + 1, len(src)
    depth = 0
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            break  # не регулярка — вернёмся к обычному скану
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif c == "/" and depth == 0:
            return i + 1
        i += 1
    return start + 1


def _expression_end(src: str, _expression_start: int) -> int:
    """Индекс `}`, закрывающего `${` (скобки и строки — с учётом вложенности)."""
    i, n, depth = _expression_start, len(src), 0
    while i < n:
        c = src[i]
        if c in "\"'`":
            i = _close_string(src, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _close_string(src: str, start: int) -> int:
    """Позиция за закрывающей кавычкой строки, начатой в `start`."""
    quote = src[start]
    i, n = start + 1, len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == quote:
            return i + 1
        if quote == "`" and src[i] == "$" and src[i + 1 : i + 2] == "{":
            i = _expression_end(src, i + 1) + 1
            continue
        i += 1
    return n


# ------------------------------------------------------------- разметка


def runs_of(markup: str) -> list[str]:
    """Текстовые куски HTML-фрагмента + значения переводимых атрибутов.

    Границей узла считается только тег: перевод строки в разметке DOM узел
    не разрезает, и «Температуру … считает\nморская модель: …» — одна фраза,
    а не три ключа. Реальный узел ищется в словаре целиком.
    """
    chunks = [v for _, v in ATTR_RE.findall(markup)]
    text = SCRIPT_RE.sub(" ", markup)
    text = STYLE_RE.sub(" ", text)
    chunks += TAG_RE.sub(SEP, text).split(SEP)
    return [c for c in chunks if has_cyrillic(c)]


def extract(path: Path) -> dict[str, list[str]]:
    """{"plain": […], "needs_template": […]} — ключи, которые обязан знать словарь."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".js":
        # Каждый литерал — самостоятельный «фрагмент разметки»: его отдаём
        # разborу отдельно, чтобы переносы строк внутри литерала не стали
        # границами ключей.
        chunks = [part for lit in scan_js(raw) for part in runs_of(lit)]
    else:
        chunks = runs_of(COMMENT_RE.sub(" ", raw))

    plain: list[str] = []
    needs: list[str] = []
    for chunk in chunks:
        pieces = [normalize(p) for p in chunk.split(SEP)]
        for idx, piece in enumerate(pieces):
            if not piece or not has_cyrillic(piece):
                continue
            neighbours = [p for j, p in enumerate(pieces) if j != idx and p]
            # Соседний непустой кусок = вставка стоит внутри фразы: её
            # надо выносить в t() шаблоном, а не докладывать в словарь.
            (needs if neighbours else plain).append(piece)
    return {"plain": dedupe(plain), "needs_template": dedupe(needs)}


def dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def skeleton(report: dict) -> dict:
    """Заготовка бандла: ключи из разметки и из данных, переводы пустые.

    Две секции — два разных контракта: `ui` обязана совпадать с кодом
    фронта (оба направления: ни дыр, ни мёртвых ключей), `labels` описывает
    подписи, которые приходят *извне* (данные квиза, подписи сервисов,
    модули фронта) и потому статикой не проверяются.
    """
    return {
        "ui": dict.fromkeys(report["front_keys"], ""),
        "labels": dict.fromkeys(report["foreign_keys"], ""),
    }


def merged_ui(path: Path = BUNDLE) -> dict:
    """Словарь, которым пользуется обходчик: `labels` + `ui` (фронт главнее)."""
    bundle = load_bundle(path)
    return {**(bundle.get("labels") or {}), **(bundle.get("ui") or {})}


def load_bundle(path: Path = BUNDLE) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def python_labels() -> set[str]:
    """Подписи, которые приходят в DOM из Python: их тоже требует словарь.

    Берём значения прямо из модулей (без парсинга): подпись WMO, дни
    недели, темы и типы из матч-мейкера, вердикты моря, названия городов
    и тексты квиза. Фронт их не печатает — их печатает сервер, и английский
    экран без этих ключей выглядел бы «переведённым наполовину».
    """
    sys.path.insert(0, str(ROOT))
    from app.services import marine, recommend, weather  # noqa: PLC0415

    out: set[str] = {normalize(w[1]) for w in weather.WMO.values() if w[1]}
    out |= {normalize(d) for d in weather.WEEKDAYS}
    out |= {normalize(n) for _, n, _, _ in weather.CITIES}
    out |= {normalize(label) for label in recommend.TAGS.values()}
    out |= {normalize(m["label"]) for m in recommend.TYPE_META.values()}
    out |= {normalize(p["title"]) for p in recommend.PROFILES.values()}
    out |= {normalize(p["summary"]) for p in recommend.PROFILES.values()}
    # Районы matching-мейкер отдаёт подписью `area_label` — её видно в фильтрах.
    out |= {normalize(label) for label in recommend.AREA_LABEL.values()}
    # Подписи моря: вердикт и волнение — функции, а не словарь. Зовём их
    # на representative значениях, числа складывает `fold_key`.
    for height in (0.1, 0.4, 0.8, 1.2, 1.8):
        out.add(normalize(marine.wave_label(height)))
    for temp, height in (
        (24.0, 0.4),
        (21.0, 0.4),
        (18.0, 0.4),
        (12.0, 0.4),
        (None, None),
    ):
        out.add(normalize(marine.verdict(temp, height)["label"]))
    for temp, height in ((24.0, 1.2), (24.0, 1.7)):
        out.add(normalize(marine.verdict(temp, height)["label"]))
    return {t for t in out if t}


def collect(sources: list[Path] | None = None, exempt: set[str] | None = None) -> dict:
    """Главный вход для теста: строки фронта и сверка со словарём.

    `exempt` — строки, которые переводить не принято (см. `EXEMPT`); через
    аргумент тест может добавить своё исключение и объяснить причину.
    """
    skip = set(EXEMPT) if exempt is None else exempt
    paths = sources or [p for p in FRONT_SOURCES if p.exists()]
    found = {p.name: extract(p) for p in paths}
    ui = merged_ui()
    front_keys = dedupe([k for part in found.values() for k in part["plain"]])
    foreign_keys = dedupe(sorted(quiz_texts() | python_labels()))
    keys = dedupe(front_keys + foreign_keys)

    # Ключ принят, если он есть буквально ИЛИ в свёрнутом виде: подпись,
    # собранную из кусков («через 5 минут»), словарю удобнее знать шаблон
    # «через {n} минут». Литералы данных («3–5 дней» и «6–10 дней»),
    # наоборот, обязаны жить буквально — иначе сворачивание чисел склеит
    # два разных варианта в один.
    missing: list[str] = []
    for key in keys:
        if key in skip:
            continue
        if key not in ui and fold_key(key) not in ui:
            missing.append(key)

    # Мёртвые ключи смотрим только в `ui`: `labels` описывает вывод функций
    # и серверных подписей, в исходниках такой строки может и не быть.
    # сверяем со списком ключей фронта, а не с текстом файлов: текст придётся
    # «сворачивать» регуляркой, а она в шаблонных строках съедает больше, чем
    # следует, — честный перевод выглядел бы мёртвым.
    front = set(front_keys)
    front_folded = {fold_key(k) for k in front_keys}
    unused = [
        key
        for key in (load_bundle().get("ui") or {})
        if key not in front and fold_key(key) not in front_folded
    ]

    return {
        "found": found,
        "keys": keys,
        "front_keys": front_keys,
        "foreign_keys": foreign_keys,
        "missing": missing,
        "needs_template": dedupe(
            [k for part in found.values() for k in part["needs_template"]]
        ),
        "unused": unused,
        "ui_total": len(ui),
    }


def quiz_texts() -> set[str]:
    """Тексты квиза: их рисует фронт из `app/data/quiz.json`, ключ — RU-строка.

    Складываются в словарь по-русски: ключ — то, что увидит DOM.
    """
    path = ROOT / "app" / "data" / "quiz.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {normalize(data.get("intro", ""))}
    for q in data.get("questions", []):
        for field in ("title", "subtitle"):
            out.add(normalize(q.get(field, "")))
        for opt in q.get("options", []):
            for field in ("label", "hint"):
                out.add(normalize(opt.get(field, "")))
    return {t for t in out if t}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--missing", action="store_true", help="только дыры в словаре")
    parser.add_argument(
        "--keys", action="store_true", help="все ключи (скелет словаря)"
    )
    parser.add_argument(
        "--skeleton", metavar="PATH", help="записать скелет словаря в JSON-файл"
    )
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    args = parser.parse_args(argv)

    report = collect()
    if args.skeleton:
        path = Path(args.skeleton)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(skeleton(report), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(
            f"{path}: ui {len(report['front_keys'])} + labels "
            f"{len(report['foreign_keys'])} ключей"
        )
        return 0
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.missing:
        print("\n".join(report["missing"]))
        return 0 if not report["missing"] else 1
    if args.keys:
        print("\n".join(report["keys"]))
        return 0

    print(f"строк интерфейса найдено: {len(report['keys'])}")
    print(f"ключей в словаре: {report['ui_total']}")
    for label, keys in (
        ("нет в словаре", report["missing"]),
        ("нужен вынос в t() шаблоном", report["needs_template"]),
        ("мёртвые ключи", report["unused"]),
    ):
        print(f"\n{label}: {len(keys)}")
        for key in keys:
            print(f"  - {key}")
    ok = not (report["missing"] or report["needs_template"] or report["unused"])
    print("\n" + ("покрытие полное" if ok else "есть замечания"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
