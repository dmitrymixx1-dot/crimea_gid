#!/usr/bin/env python3
"""Оптимизация изображений `static/img` (dev-инструмент, не рантайм).

Картинки каталога и hero весят сотни килобайт каждая при отображении
в карточках 255–560 px: ресайз + качество + progressive JPEG срезают
вес в ~4 раза без видимых потерь. Бюджет веса зафиксирован тестом
`tests/test_assets.py::test_image_weight_budget` — после правки картинок
прогоняйте его.

Использование:
    pip install pillow          # dev-зависимость, в requirements.txt не входит
    python tools/optimize_images.py            # перезаписать картинки
    python tools/optimize_images.py --check    # только показать текущий вес

Идемпотентно: повторный прогон поверх уже сжатых файлов почти не меняет
вес (ресайз до тех же размеров + то же качество).
"""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover — подсказка вместо traceback
    sys.exit("Нужен pillow: pip install pillow")

IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "img"

# имя -> (ширина, качество JPEG). Высота — по исходной пропорции.
HERO = ("hero.jpg", 1200, 76)
CATS = 760, 72

# Бюджет веса (байт) — зеркало tests/test_assets.py.
BUDGET_HERO = 220_000
BUDGET_CAT = 130_000
BUDGET_TOTAL = 1_300_000


def targets():
    yield IMG_DIR / HERO[0], HERO[1], HERO[2], BUDGET_HERO
    for p in sorted(IMG_DIR.glob("cat_*.jpg")):
        yield p, CATS[0], CATS[1], BUDGET_CAT


def optimize(path: Path, width: int, quality: int) -> tuple[int, int]:
    before = path.stat().st_size
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            height = round(im.height * width / im.width)
            im = im.resize((width, height), Image.LANCZOS)
        im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return before, path.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="не перезаписывать, только сверить вес с бюджетом")
    args = parser.parse_args()

    total = 0
    over = []
    for path, width, quality, budget in targets():
        if not path.exists():
            continue
        if args.check:
            size = path.stat().st_size
        else:
            _, size = optimize(path, width, quality)
            print(f"{path.name}: -> {size / 1024:.0f} КБ")
        total += size
        if size > budget:
            over.append(f"{path.name}: {size} > {budget}")
    for p in sorted(IMG_DIR.glob("*.png")):
        total += p.stat().st_size
    print(f"итого static/img: {total / 1024:.0f} КБ (бюджет {BUDGET_TOTAL // 1024} КБ)")
    if total > BUDGET_TOTAL:
        over.append(f"total: {total} > {BUDGET_TOTAL}")
    if over:
        print("ПРЕВЫШЕН БЮДЖЕТ:\n  " + "\n  ".join(over))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
