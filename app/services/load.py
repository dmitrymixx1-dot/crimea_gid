"""Загрузка JSON-данных из app/data с простым кэшированием."""
import json
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@cache
def _read(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def get_attractions() -> list[dict]:
    return _read("attractions.json")


def get_quiz() -> dict:
    return _read("quiz.json")


def get_sources() -> list[dict]:
    return _read("sources.json")


def get_snapshot() -> dict:
    return _read("news_snapshot.json")
