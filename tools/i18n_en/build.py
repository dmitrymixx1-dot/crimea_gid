"""Сборка `static/i18n/en.json`.

Требуемые ключи диктует `tools/i18n_extract.py`, переводы лежат рядом:
`tr_ui.py` (интерфейс и подписи) и `tr_places.py` (каталог по id места).
Ключ словаря — русская строка-источник, поэтому расхождение с кодом видно
сразу: «не переведено» или «лишний ключ».

    .venv/bin/python tools/i18n_en/build.py            # собрать
    .venv/bin/python tools/i18n_en/build.py --check     # проверить, что актуально
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(1, str(HERE))

import i18n_extract as X  # noqa: E402
from tr_places import PLACES  # noqa: E402
from tr_ui import EXTRA_LABELS, LABELS, UI  # noqa: E402

EXEMPT = X.EXEMPT  # причины исключений — в инструменте, они относятся к исходникам

BUNDLE = ROOT / "static" / "i18n" / "en.json"


def norm(text):
    return " ".join(text.split())


def match_map(need, mine):
    """Разложить переводы по требуемым ключам; несовпадения — в репорт.

    Ключ может быть записан и до свёртки чисел, и после: «3–5 дней» в коде и
    «{n}–{n} дней» в списке — один и тот же перевод.
    """
    by_norm = {norm(k): v for k, v in mine.items() if norm(k) not in EXEMPT}
    folded = {X.fold_key(k): k for k in by_norm}
    out, unmatched = {}, []
    for key in need:
        if key in EXEMPT:
            continue
        if key in by_norm:
            out[key] = by_norm[key]
            continue
        if X.fold_key(key) in folded:
            out[key] = by_norm[folded[X.fold_key(key)]]
            continue
        near = difflib.get_close_matches(key, list(by_norm), n=1, cutoff=0.82)
        # «Близко» — только подсказка человеку: опечатку в переводе оставлять
        # нельзя, иначе «для двоих» приедет на место «Для двоих».
        unmatched.append(("близко" if near else "нет", key, near[0] if near else ""))
    used = {norm(x) for x in out}
    leftover = [k for k in by_norm if norm(k) not in used]
    return out, unmatched, leftover


def build(verbose=True):
    """Текст бандла и список расхождений переводов с требуемыми ключами.

    Второй элемент — не лог, а код возврата: `--check` и `test_i18n.py`
    обязаны падать на любой дыре, а не печатать её «для информации».
    """
    report = X.collect()
    need_ui, need_labels = report["front_keys"], report["foreign_keys"]

    ui, ui_unmatched, ui_left = match_map(need_ui, UI)
    labels, labels_unmatched, labels_left = match_map(
        need_labels, LABELS | EXTRA_LABELS
    )
    labels.update(EXTRA_LABELS)  # вне обязательного списка, но нужны фронту
    # Обходчик живёт одним словарём {...labels, ...ui}; если строка нужна и
    # разметке, и данным, держим её в `ui` — там проверка двусторонняя.
    labels = {k: v for k, v in labels.items() if k not in ui}

    merged = {**labels, **ui}  # им пользуется обходчик, его и сверяем
    missing = [k for k in need_ui + need_labels if k not in merged and k not in EXEMPT]
    problems = (
        ui_unmatched
        + labels_unmatched
        + [
            ("лишний", key, "")
            for kind, items in (("ui", ui_left), ("labels", labels_left))
            for key in items
            if key
            not in EXTRA_LABELS  # запас на случай, что фронт соберёт строку иначе
        ]
        + [("не переведено", key, "") for key in missing]
    )
    for why, key, near in problems:
        # Расхождение интересно всегда: и при сборке, и в --check (его ловит тест).
        print(f"[{why}]: {key!r}" + (f"  <->  {near!r}" if near else ""))
    if verbose:
        print(
            f"ключей: ui {len(ui)} (из {len(need_ui)}), "
            f"labels {len(labels)} (из {len(need_labels)} треб.), "
            f"places {len(PLACES)}"
        )

    bundle = {
        "lang": "en",
        "name": "English",
        "_comment": (
            "Английский пакет интерфейса. Ключ словаря — русская строка ровно "
            "так, как её видит DOM: 'ui' обязана совпадать с кодом фронта "
            "(проверка двусторонняя — tests/test_i18n.py), 'labels' закрывает "
            "подписи, приходящие из данных и модулей, а 'places' переводит "
            "каталог по id. Ключ с {n} — свёрнутая подпись: числа в неё "
            "подставляет I18n.fold()."
        ),
        "ui": ui,
        "labels": labels,
        "places": PLACES,
    }
    return json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="не писать файл, а сверить с тем, что лежит в репозитории",
    )
    args = parser.parse_args()
    text, problems = build(verbose=not args.check)
    if problems:
        print(f"расхождений со словарём: {len(problems)}")
        return 1
    if args.check:
        current = BUNDLE.read_text(encoding="utf-8") if BUNDLE.exists() else ""
        if current != text:
            print(f"{BUNDLE} устарел — перегенерируйте: tools/i18n_en/build.py")
            return 1
        print("бандл актуален")
        return 0
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE.write_text(text, encoding="utf-8")
    print(f"записано: {BUNDLE} ({BUNDLE.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
